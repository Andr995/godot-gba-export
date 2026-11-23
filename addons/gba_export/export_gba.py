"""Driver CLI/editor: analisi, generazione, make e verifica limiti ELF/ROM."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from assets import ExportError
from compiler import compile_scene

HERE = Path(__file__).resolve().parent


def run(command, cwd=None, timeout=180):
    print('Esecuzione:', ' '.join(str(x) for x in command), flush=True)
    try:
        completed=subprocess.run(command,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                 timeout=timeout,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except subprocess.TimeoutExpired as exc:
        raise ExportError('build',1,f'Timeout dopo {timeout}s: {command[0]}','TOOL002') from exc
    except OSError as exc:
        raise ExportError('build',1,f'Impossibile avviare {command[0]}: {exc}','TOOL001') from exc
    encoding='utf-16-le' if completed.stdout[:100].count(b'\0')>15 else 'utf-8'
    output=completed.stdout.decode(encoding,errors='replace')
    if output: print(output.rstrip(),flush=True)
    if completed.returncode:
        raise ExportError('build',1,f'Comando terminato con codice {completed.returncode}: {command[0]}','TOOL003')
    return output


def toolchain():
    local=Path('tools/gba/sdk')
    sdk=Path(os.environ.get('DEVKITPRO',str(local)))
    arm=Path(os.environ.get('DEVKITARM',str(sdk/'devkitARM')))
    exe='.exe' if os.name=='nt' else ''
    if (arm/'bin'/('arm-none-eabi-gcc'+exe)).is_file():
        make=shutil.which('make') or shutil.which('mingw32-make')
        if make is None: raise ExportError('project.godot',1,'GNU make mancante nel PATH','TOOL001')
        for component in ('libtonc/include/tonc.h','libtonc/lib/libtonc.a','libgba/include/maxmod.h','libgba/lib/libmm.a','tools/bin/mmutil'+exe,'tools/bin/gbafix'+exe):
            if not (sdk/component).is_file(): raise ExportError('project.godot',1,'devkitPro incompleto: manca '+component,'TOOL001')
        return {'host':'native','sdk':str(sdk),'arm':str(arm),'make':make,'exe':exe}
    if os.name=='nt' and (local/'devkitARM/bin/arm-none-eabi-gcc').is_file() and shutil.which('wsl'):
        return {'host':'wsl','distro':os.environ.get('GBA_WSL_DISTRO','Ubuntu')}
    raise ExportError('project.godot',1,'devkitPro/devkitARM mancante. Installare gba-dev (libtonc, Maxmod, mmutil, gbafix) e make; oppure python addons/gba_export/setup_sdk.py --sdk-only per SDK locale Linux/WSL.','TOOL001')


def elf_info(path):
    data=path.read_bytes()
    if data[:7]!=b'\x7fELF\x01\x01\x01': raise ExportError(path,1,'Atteso ELF ARM32 little endian')
    if struct.unpack_from('<H',data,18)[0]!=40: raise ExportError(path,1,'ELF non ARM')
    offset=struct.unpack_from('<I',data,32)[0]
    entry_size,count=struct.unpack_from('<HH',data,46)
    sections=[struct.unpack_from('<10I',data,offset+i*entry_size) for i in range(count)]
    symbols={}
    budgets={'iwram':0,'ewram':0}
    for section in sections:
        _,kind,flags,address,file_offset,size,link,_,_,step=section
        if flags&2:
            for name,base,capacity in [('iwram',0x03000000,32768),('ewram',0x02000000,262144)]:
                if base<=address<base+capacity and size: budgets[name]=max(budgets[name],address+size-base)
        if kind==2:
            string_table=sections[link]
            strings=data[string_table[4]:string_table[4]+string_table[5]]
            for i in range(0,size,step):
                name,value,symbol_size,_,_,_=struct.unpack_from('<IIIBBH',data,file_offset+i)
                end=strings.find(b'\0',name)
                label=strings[name:end].decode('utf-8','replace')
                if label: symbols[label]={'address':value,'size':symbol_size}
    if budgets['iwram']>28672: raise ExportError(path,1,'IWRAM oltre 28 KiB: riservati 4 KiB per stack/IRQ')
    if budgets['ewram']>196608: raise ExportError(path,1,'EWRAM oltre 192 KiB: riservati 64 KiB per heap/audio/stack')
    return budgets,symbols


def build_native(work, metadata):
    tc=toolchain()
    if tc['host']!='native': raise ExportError('build',1,'Backend make richiede toolchain nativa')
    sdk=os.path.relpath(tc['sdk'],work).replace('\\','/')
    arm=os.path.relpath(tc['arm'],work).replace('\\','/')
    if any(c in sdk+arm for c in '\n\r#$'): raise ExportError('build',1,'Percorso SDK non supportato da make')
    suffix=tc['exe']
    audio=metadata['sounds']>0
    if audio:
        inputs=[f'sample_{i:03d}.wav' for i in range(metadata['sounds'])]
        mmutil=os.path.join(sdk,'tools','bin','mmutil'+suffix)
        run([mmutil,*inputs,'-osoundbank.bin','-hsoundbank.h'],cwd=work)
        bank=(work/'soundbank.bin').read_bytes()
        if len(bank)>32*1024*1024: raise ExportError(work/'soundbank.bin',1,'Soundbank oltre 32 MiB')
        (work/'soundbank.S').write_text('.section .rodata.soundbank,"a",%progbits\n.balign 4\n.global soundbank\nsoundbank:\n.incbin "soundbank.bin"\n',encoding='ascii')
    objects=' '.join(name+'.o' for name in metadata.get('c_sources',['runtime','generated']))+(' soundbank.o' if audio else '')
    optimize='-O2'
    makefile=f'''SDK := {sdk}
ARM := {arm}
CC := $(ARM)/bin/arm-none-eabi-gcc{suffix}
OBJCOPY := $(ARM)/bin/arm-none-eabi-objcopy{suffix}
CFLAGS := -std=c11 {optimize} -g -mthumb -mthumb-interwork -mcpu=arm7tdmi -ffunction-sections -fdata-sections -Wall -Wextra -Werror -Wno-misleading-indentation -I. -I"$(SDK)/libtonc/include" -I"$(SDK)/libgba/include"
.PHONY: all
all: game.gba
%.o: %.c runtime.h
\t"$(CC)" $(CFLAGS) -c "$<" -o "$@"
soundbank.o: soundbank.S soundbank.bin
\t"$(CC)" -mthumb -mcpu=arm7tdmi -c soundbank.S -o soundbank.o
game.elf: {objects}
\t"$(CC)" -mthumb -mthumb-interwork -mcpu=arm7tdmi -specs=gba.specs -Wl,-Map,game.map -Wl,--gc-sections {objects} -L"$(SDK)/libtonc/lib" -L"$(SDK)/libgba/lib" -lmm -ltonc -lm -o "$@"
game.gba: game.elf
\t"$(OBJCOPY)" -O binary "$<" "$@"
\t"$(SDK)/tools/bin/gbafix{suffix}" "$@" -tGODOTGBA -cGGBA -m00
'''
    (work/'Makefile').write_text(makefile,encoding='utf-8',newline='\n')
    # DrvFS e il clock WSL possono differire di meno di un secondo.
    timestamp=time.time()-5
    for source in work.iterdir():
        if source.suffix in ('.c','.h','.S','.bin') or source.name=='Makefile': os.utime(source,(timestamp,timestamp))
    # -B evita output obsoleto cambiando scena, configurazione o SDK.
    run([tc['make'],'-B','-j2'],cwd=work)
    return tc


def main_scene():
    project=Path('project.godot')
    if not project.is_file(): raise ExportError(project,1,'project.godot non trovato')
    for number,line in enumerate(project.read_text(encoding='utf-8-sig').splitlines(),1):
        match=re.fullmatch(r'\s*run/main_scene="res://([^"\n]+)"\s*',line)
        if match: return Path(match[1])
    raise ExportError(project,1,'run/main_scene deve essere un percorso res:// esplicito (.tscn); UID non supportato')


def check_project():
    section=''
    for number,line in enumerate(Path('project.godot').read_text(encoding='utf-8-sig').splitlines(),1):
        text=line.strip()
        if text.startswith('[') and text.endswith(']'): section=text[1:-1]
        elif text and not text.startswith(';') and section=='autoload':
            raise ExportError('project.godot',number,'Autoload non convertibile; integrare esplicitamente la logica nella scena GBA')
    print('Target GBA: viewport 240x160 a circa 59,73 Hz; coordinate 1:1, nessun ridimensionamento automatico. Solo risorse raggiunte dalla scena selezionata.',flush=True)


def inventory():
    result={'scripts':[],'png':[],'wav_count':0,'wav_bytes':0,'level_count':len(list(Path('data/levels').glob('*.json')))}
    patterns=[(r'\b(Dictionary|Variant|Callable|Array)\b','GDScript dinamico non compreso nel sottoinsieme numerico'),
              (r'\b(FileAccess|DirAccess)\b','Filesystem Godot: richiede un port SRAM/Flash'),
              (r'\b(ShaderMaterial|Shader)\b','Shader Godot non eseguibile su GBA'),
              (r'\b(Label|Button|Control|LineEdit|TouchScreenButton)\.new\(','UI/periferiche dinamiche: serve un port GBA'),
              (r'\b[a-zA-Z_]\w*\.new\(','Allocazione dinamica di oggetti Godot non supportata'),
              (r'\b(DisplayServer|OS)\.','API host non disponibili nel runtime GBA'),
              (r'\bdraw_\w+\(','Disegno immediato Godot: convertire in sprite/BG statici')]
    for script in sorted(Path('scripts').glob('*.gd')):
        lines=script.read_text(encoding='utf-8-sig').splitlines()
        features=[]
        for expression,description in patterns:
            for number,line in enumerate(lines,1):
                if re.search(expression,line): features.append({'line':number,'reason':description}); break
        result['scripts'].append({'file':script.as_posix(),'lines':len(lines),'unsupported':features})
    for png in sorted(Path('assets').rglob('*.png')):
        with png.open('rb') as source: header=source.read(24)
        if header[:8]==b'\x89PNG\r\n\x1a\n': result['png'].append({'file':png.as_posix(),'size':list(struct.unpack_from('>II',header,16))})
    for wav in Path('assets').rglob('*.wav'):
        result['wav_count']+=1; result['wav_bytes']+=wav.stat().st_size
    return result


def checked_output(value):
    out=Path(value)
    root=Path('.').resolve()
    if not out.resolve().is_relative_to(root) or not out.resolve().is_relative_to((root/'build').resolve()) or out.resolve()==(root/'build').resolve():
        raise ExportError('build',1,'Output consentito solo in una sottocartella di build/')
    out.mkdir(parents=True,exist_ok=True)
    (out/'.gdignore').touch()
    marker=out/'.gba_export_output'
    if (out/'game.gba').exists() and not marker.exists(): raise ExportError(out,1,'Output non posseduto dall’exporter: scegliere una cartella nuova')
    marker.write_text('Godot GBA Export 1\n',encoding='ascii')
    # Una vecchia ROM resta consultabile, ma non deve sembrare il risultato della build fallita.
    if (out/'game.gba').exists(): (out/'game.gba').replace(out/'game.previous.gba')
    return out


def execute(args):
    out=checked_output(args.out)
    work=out/'work'; work.mkdir(exist_ok=True)
    report={'status':'failed','rom':None,'diagnostics':[],'inventory':inventory()}
    try:
        selected=Path(args.scene) if args.scene else main_scene()
        if not selected.resolve().is_relative_to(Path('.').resolve()): raise ExportError(selected,1,'Scena esterna al progetto')
        check_project()
        print('Scena selezionata:',selected.as_posix(),flush=True)
        if args.scene: print('SCENA ESPLICITA: questa build non certifica la conversione della scena principale del progetto.',flush=True)
        try: tc=toolchain()
        except ExportError as error:
            tc=None
            print(error,flush=True)
            if not args.analyze: report['diagnostics'].append(str(error))
        metadata=compile_scene(Path('.'),selected,work,args.bpp)
        report['conversion']=metadata
        if args.analyze:
            report['status']='analysis_passed'
            return 0
        if tc is None: raise ExportError('project.godot',1,'Compilazione non eseguita: toolchain mancante','TOOL001')
        (work/'conversion.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        if tc['host']=='wsl':
            relative=Path(__file__).resolve().relative_to(Path('.').resolve()).as_posix()
            command=['wsl','-d',tc['distro'],'--exec','python3',relative,'--make-only','--out',work.as_posix()]
            run(command,timeout=240)
        else: build_native(work,metadata)
        rom=work/'game.gba'
        raw=rom.read_bytes()
        if not 192<=len(raw)<=32*1024*1024: raise ExportError(rom,1,'Dimensione ROM fuori dai limiti GBA')
        if raw[0xb2]!=0x96 or ((sum(raw[0xa0:0xbd])+0x19+raw[0xbd])&255)!=0:
            raise ExportError(rom,1,'Header/checksum GBA non valido')
        budgets,symbols=elf_info(work/'game.elf')
        (out/'symbols.json').write_text(json.dumps(symbols,indent=2),encoding='utf-8')
        shutil.copyfile(rom,out/'game.gba')
        report.update(status='built',rom=(out/'game.gba').as_posix(),rom_bytes=len(raw),rom_sha256=hashlib.sha256(raw).hexdigest(),memory=budgets,toolchain=tc)
        print(f'PASS build: {out.as_posix()}/game.gba ({len(raw)} byte); IWRAM {budgets["iwram"]}/32768; EWRAM statica {budgets["ewram"]}/262144.',flush=True)
        print('ROM compilata. Verificare rendering, input e logica del proprio gioco in mGBA.',flush=True)
        return 0
    except (ExportError,OSError,ValueError,KeyError,TypeError,struct.error) as error:
        diagnostic=str(error) if isinstance(error,ExportError) else f'build:1: error INTERNAL: {type(error).__name__}: {error}'
        report['diagnostics'].append(diagnostic)
        print(diagnostic,flush=True)
        if not args.scene:
            for script in report['inventory']['scripts']:
                for feature in script['unsupported']:
                    print(f'{script["file"]}:{feature["line"]}: error AUDIT: {feature["reason"]}',flush=True)
        print('EXPORT FALLITO: nessuna nuova ROM del gioco. Consultare README.md del plugin e readme.md della distribuzione.',flush=True)
        return 2
    finally:
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',default='.')
    parser.add_argument('--scene',help='Scena esplicita solo per port/test: non sostituisce automaticamente main_scene')
    parser.add_argument('--out',default='build/gba')
    parser.add_argument('--bpp',type=int,choices=(4,8),default=8)
    parser.add_argument('--profile',choices=('strict',),default='strict',help='Compilatore generico a sottoinsieme esplicito')
    parser.add_argument('--analyze',action='store_true')
    parser.add_argument('--make-only',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--log')
    args=parser.parse_args()
    os.chdir(args.project)
    if args.log:
        log=Path(args.log)
        if not log.resolve().is_relative_to(Path('.').resolve()) or not log.resolve().is_relative_to((Path('.')/'build').resolve()): parser.error('Log consentito solo in build/')
        log.parent.mkdir(parents=True,exist_ok=True)
        sys.stdout=log.open('w',encoding='utf-8',buffering=1)
        sys.stderr=sys.stdout
    try:
        if args.make_only:
            work=Path(args.out)
            if not work.resolve().is_relative_to(Path('build').resolve()): raise ExportError(work,1,'make-only richiede output in build/')
            build_native(work,json.loads((work/'conversion.json').read_text(encoding='utf-8')))
            return 0
        return execute(args)
    except ExportError as error:
        print(error,flush=True)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
