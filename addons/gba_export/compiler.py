"""Abbassamento scene statiche/risorse/script al runtime C libtonc."""
from pathlib import Path
import math
import re
import shutil
from assets import ExportError, read_png, make_palette, tiles, obj_size, convert_wav, c_array, rgb555
from scene import Call, parse, vector, local_path, tile_cells, literal
from gdscript import Script

NODE_TYPES = {'Node2D', 'Sprite2D', 'CharacterBody2D', 'StaticBody2D', 'CollisionShape2D', 'AudioStreamPlayer', 'TileMapLayer'}
COMMON = {'position','visible','z_index','script'}
PROPERTIES = {
    'Node2D': set(),
    'Sprite2D': {'texture','hframes','vframes','frame','flip_h','flip_v','centered','offset'},
    'CharacterBody2D': {'collision_layer','collision_mask','motion_mode'},
    'StaticBody2D': {'collision_layer','collision_mask'},
    'CollisionShape2D': {'shape','one_way_collision'},
    'AudioStreamPlayer': {'stream','autoplay','volume_db'},
    'TileMapLayer': {'tile_set','tile_map_data','enabled'},
}


def compile_scene(root, path, out, bpp=8):
    sections = parse(path)
    externals, resources, nodes = {}, {}, []
    for section in sections:
        if section.kind == 'ext_resource':
            if set(section.attrs) - {'type','path','id','uid'}: raise ExportError(path,section.line,'Attributi ext_resource non supportati')
            externals[str(section.attrs['id'])] = section
        elif section.kind == 'sub_resource':
            if section.attrs.get('type') not in ('RectangleShape2D','TileSet','TileSetAtlasSource'):
                raise ExportError(path,section.line,'Risorsa non convertibile: '+str(section.attrs.get('type')))
            resources[str(section.attrs['id'])] = section
        elif section.kind == 'node':
            if set(section.attrs) - {'name','type','parent'}:
                raise ExportError(path,section.line,'Scene istanziate, owner, gruppi e attributi nodo aggiuntivi non supportati')
            kind = section.attrs.get('type')
            if kind not in NODE_TYPES: raise ExportError(path,section.line,'Tipo nodo non convertibile: '+str(kind))
            for key in section.props:
                if key not in COMMON | PROPERTIES[kind]: raise ExportError(path,section.lines[key],'Proprietà non convertibile: '+key)
            parent_name = section.attrs.get('parent')
            if parent_name is None:
                if nodes: raise ExportError(path,section.line,'Radice scena duplicata')
                parent, full = -1, '.'
            else:
                parent = next((n['index'] for n in nodes if n['path']==parent_name), -1)
                if parent < 0: raise ExportError(path,section.line,'Parent deve precedere il figlio')
                full = section.attrs['name'] if parent_name=='.' else parent_name+'/'+section.attrs['name']
            if any(n['path']==full for n in nodes): raise ExportError(path,section.line,'Percorso nodo duplicato')
            props = section.props
            pos = vector(props.get('position',Call('Vector2',[0,0])),path,section.lines.get('position',section.line))
            if not all(math.isfinite(v) and abs(v)<=32767 for v in pos): raise ExportError(path,section.line,'Coordinate non finite o oltre ±32767')
            for key,value in props.items():
                if key in {'visible','flip_h','flip_v','centered','autoplay','enabled','one_way_collision'} and type(value)!=bool:
                    raise ExportError(path,section.lines[key],'Proprietà booleana richiesta: '+key)
                if key in {'z_index','hframes','vframes','frame','collision_layer','collision_mask','motion_mode'} and type(value)!=int:
                    raise ExportError(path,section.lines[key],'Proprietà intera richiesta: '+key)
                if key in {'collision_layer','collision_mask'} and not 0<=value<=0xffffffff:
                    raise ExportError(path,section.lines[key],'Layer/mask fuori dai 32 bit')
            if props.get('z_index',0)!=0 and kind!='Sprite2D': raise ExportError(path,section.lines['z_index'],'z_index supportato solo direttamente su Sprite2D')
            nodes.append({'index':len(nodes),'path':full,'parent':parent,'type':kind,'pos':pos,'section':section,
                          'shape':-1,'sprite':-1,'visible':int(props.get('visible',True)), 'z':props.get('z_index',0)})
        elif section.kind not in ('gd_scene',): raise ExportError(path,section.line,'Sezione non convertibile: '+section.kind)
    if not nodes or len(nodes)>256: raise ExportError(path,1,'Richiesti da 1 a 256 nodi statici')

    def resource(value, expected, section):
        if not isinstance(value,Call) or len(value.args)!=1: raise ExportError(path,section.line,'Riferimento risorsa richiesto: '+expected)
        if value.name=='ExtResource' and str(value.args[0]) in externals:
            ext = externals[str(value.args[0])]
            if ext.attrs['type'] != expected: raise ExportError(path,ext.line,'Tipo risorsa errato; atteso '+expected)
            return local_path(root,ext.attrs['path'],path,ext.line)
        if value.name=='SubResource' and str(value.args[0]) in resources:
            result=resources[str(value.args[0])]
            if result.attrs['type']!=expected: raise ExportError(path,result.line,'Tipo risorsa errato; atteso '+expected)
            return result
        raise ExportError(path,section.line,'Risorsa non risolta: '+expected)

    def check_props(section, allowed):
        for prop in section.props:
            if prop not in allowed: raise ExportError(path,section.lines[prop],'Proprietà risorsa non convertibile: '+prop)

    images, sprite_list, shape_list, sounds, bg_list = {}, [], [], [], []
    def image(asset):
        if not isinstance(asset,Path) or asset.suffix.lower()!='.png': raise ExportError(path,1,'Richiesta texture PNG esterna')
        if asset not in images: images[asset]=read_png(asset)
        return images[asset]

    for node in nodes:
        section=node['section']; p=section.props; kind=node['type']
        if kind=='Sprite2D':
            texture=resource(p.get('texture'),'Texture2D',section)
            data=image(texture)
            hf,vf=p.get('hframes',1),p.get('vframes',1)
            if type(hf)!=int or type(vf)!=int or min(hf,vf)<1 or data[0]%hf or data[1]%vf:
                raise ExportError(path,section.line,'Dimensioni atlante/hframes/vframes non divisibili')
            w,h=data[0]//hf,data[1]//vf
            ow,oh,shape,size=obj_size(w,h,texture)
            if type(p.get('frame',0))!=int or not 0<=p.get('frame',0)<hf*vf: raise ExportError(path,section.line,'Frame iniziale fuori atlante')
            sprite_list.append(dict(node=node['index'],texture=texture,w=ow,h=oh,fw=w,fh=h,hf=hf,vf=vf,shape=shape,size=size,
                                    centered=int(p.get('centered',True)),offset=vector(p.get('offset',Call('Vector2',[0,0])),path,section.line)))
        elif kind=='CollisionShape2D':
            parent=nodes[node['parent']] if node['parent']>=0 else None
            if not parent or parent['type'] not in ('CharacterBody2D','StaticBody2D'): raise ExportError(path,section.line,'CollisionShape2D richiede un corpo rettangolare diretto')
            if parent['shape']!=-1: raise ExportError(path,section.line,'Supportata una sola shape per corpo')
            shape=resource(p.get('shape'),'RectangleShape2D',section)
            if isinstance(shape,Path): raise ExportError(path,section.line,'Shape esterne .tres non supportate')
            check_props(shape,{'size'})
            size=vector(shape.props.get('size',Call('Vector2',[20,20])),path,shape.line)
            if min(size)<=0: raise ExportError(path,shape.line,'Dimensioni collisione devono essere positive')
            if not all(math.isfinite(v) and v<=32767 for v in size): raise ExportError(path,shape.line,'Dimensioni collisione non finite/fuori intervallo')
            body=parent['section'].props
            if body.get('motion_mode',0)!=0: raise ExportError(path,parent['section'].line,'Solo motion_mode grounded')
            parent['shape']=len(shape_list)
            shape_list.append([parent['index'],*node['pos'],*size,body.get('collision_layer',1),body.get('collision_mask',1),int(p.get('one_way_collision',False))])
        elif kind=='AudioStreamPlayer':
            source=resource(p.get('stream'),'AudioStream',section)
            if not isinstance(source,Path) or source.suffix.lower()!='.wav': raise ExportError(path,section.line,'Audio supportato: WAV PCM esterno')
            volume=p.get('volume_db',0)
            if not isinstance(volume,(float,int)) or not -80<=volume<=0: raise ExportError(path,section.line,'volume_db supportato: da -80 a 0 dB')
            node['sound']=len(sounds); node['volume']=round(255*10**(volume/20))
            sounds.append((source,node['volume'],bool(p.get('autoplay',False))))
        elif kind=='TileMapLayer':
            if not p.get('enabled',True) or not node['visible']: raise ExportError(path,section.line,'TileMapLayer disabilitata/non visibile: rimuoverla esplicitamente dalla scena da esportare')
            tile_set=resource(p.get('tile_set'),'TileSet',section)
            if isinstance(tile_set,Path): raise ExportError(path,section.line,'TileSet .tres esterno non supportato; usare sub_resource')
            check_props(tile_set,{'tile_size'}|{k for k in tile_set.props if re.fullmatch(r'sources/\d+',k)})
            tile_size=vector(tile_set.props.get('tile_size',Call('Vector2i',[16,16])),path,tile_set.line)
            if tile_size[0] not in (8,16,32) or tile_size[1] not in (8,16,32): raise ExportError(path,tile_set.line,'TileSize supportato: 8,16,32 pixel per asse')
            atlas={}
            for key,value in tile_set.props.items():
                if not key.startswith('sources/'): continue
                source=resource(value,'TileSetAtlasSource',tile_set)
                if isinstance(source,Path): raise ExportError(path,tile_set.line,'Atlas esterno non supportato')
                for key2,v in source.props.items():
                    if key2 in ('texture','texture_region_size'): continue
                    if re.fullmatch(r'\d+:\d+/0',key2) and v==0: continue
                    raise ExportError(path,source.lines[key2],'TileData non convertibile (animazioni, terrain, poligoni e alternative esclusi): '+key2)
                region=vector(source.props.get('texture_region_size',Call('Vector2i',[16,16])),path,source.line)
                if region!=tile_size: raise ExportError(path,source.line,'texture_region_size deve coincidere con tile_size')
                tex=resource(source.props.get('texture'),'Texture2D',source)
                image(tex)
                atlas[int(key.split('/')[1])]=(tex,source)
            cells=tile_cells(p.get('tile_map_data',Call('PackedByteArray',[])),path,section.lines.get('tile_map_data',section.line))
            bg_list.append(dict(node=node['index'],size=tile_size,atlas=atlas,cells=cells,line=section.line))

    if len(sprite_list)>128: raise ExportError(path,1,'Superati 128 sprite OAM')
    if len(bg_list)>4: raise ExportError(path,1,'Superati 4 background hardware')
    if len(shape_list)>128: raise ExportError(path,1,'Superate 128 collisioni statiche/runtime')
    if len(sounds)>8: raise ExportError(path,1,'Superati 8 AudioStreamPlayer del runtime Maxmod')
    if sum(s['w']+8 for s in sprite_list)>960: raise ExportError(path,1,'Budget prudenziale sprite per scanline superato (960 cicli equivalenti)')
    for n in nodes:
        if n['type']=='CharacterBody2D' and n['shape']<0: raise ExportError(path,n['section'].line,'CharacterBody2D senza collisione rettangolare')
    characters=[s for s in shape_list if nodes[s[0]]['type']=='CharacterBody2D']
    for a in characters:
        if any(a!=b and a[6]&b[5] for b in characters): raise ExportError(path,1,'Collisioni fra CharacterBody2D non supportate; usare layer/mask distinti')

    # Compilare tutti gli script prima di scrivere output o convertire audio.
    declarations, functions = [], []
    for node in nodes:
        section=node['section']
        if 'script' not in section.props: continue
        if node['type'] not in ('Node2D','CharacterBody2D','Sprite2D'): raise ExportError(path,section.lines['script'],'Script su questo tipo di nodo non supportato')
        script=resource(section.props['script'],'Script',section)
        if not isinstance(script,Path) or script.suffix!='.gd': raise ExportError(path,section.line,'Richiesto script GDScript testuale')
        dec,func=Script(script,node,nodes).compile()
        declarations.extend(dec); functions.append((node['index'],func))

    out.mkdir(parents=True,exist_ok=True)
    sprite_list.sort(key=lambda s:(nodes[s['node']]['z'],s['node']),reverse=True)
    obj_palette,obj_colors=make_palette([images[s['texture']] for s in sprite_list],bpp)
    bg_images=[images[tex] for bg in bg_list for tex,_ in bg['atlas'].values()]
    bg_palette,bg_colors=make_palette(bg_images,bpp)
    # Il colore di cancellazione è l'indice zero comune ai BG, non un asset aggiunto.
    for number,line in enumerate(Path('project.godot').read_text(encoding='utf-8-sig').splitlines(),1):
        if line.startswith('environment/defaults/default_clear_color='):
            color=literal(line.split('=',1)[1],Path('project.godot'),number)
            if not isinstance(color,Call) or color.name!='Color' or len(color.args)!=4 or not all(isinstance(v,(int,float)) and 0<=v<=1 for v in color.args):
                raise ExportError('project.godot',number,'default_clear_color richiede Color RGBA normalizzato')
            bg_palette[0]=rgb555(tuple(round(v*255) for v in color.args))
    output=['#include "runtime.h"\n']
    obj_vram=0
    rows=[]
    for i,sprite in enumerate(sprite_list):
        data=images[sprite['texture']]
        frame_bytes=sprite['w']*sprite['h']*bpp//8
        all_frames=b''.join(tiles(data,obj_colors,bpp,(x*sprite['fw'],y*sprite['fh'],sprite['fw'],sprite['fh']),(sprite['w'],sprite['h'])) for y in range(sprite['vf']) for x in range(sprite['hf']))
        output.append(c_array('sprite_'+str(i),all_frames))
        row=[sprite['node'],sprite['w'],sprite['h'],sprite['fw'],sprite['fh'],sprite['hf']*sprite['vf'],sprite['shape'],sprite['size'],obj_vram//32,frame_bytes,sprite['centered'],*sprite['offset']]
        rows.append('{'+','.join(map(str,row))+',sprite_'+str(i)+'}')
        obj_vram+=frame_bytes
        nodes[sprite['node']]['sprite']=i
    if obj_vram>16384: raise ExportError(path,1,'Superato budget di upload OBJ per VBlank: 16 KiB (VRAM OBJ totale 32 KiB)')
    output.append('const Sprite sprites[] = {'+(','.join(rows) or '{0}')+'};\n')
    tile_bytes=64 if bpp==8 else 32
    bg_tiles=bytearray(tile_bytes); dedup={bytes(tile_bytes):0}; bg_rows=[]
    for i,bg in enumerate(bg_list):
        screen=[0]*1024
        for x,y,source,ax,ay,alternative in bg['cells']:
            if alternative: raise ExportError(path,bg['line'],'Alternative/flip/trasposizione TileMap non supportati')
            if source not in bg['atlas']: raise ExportError(path,bg['line'],'Source ID TileMap non trovato')
            texture,atlas=bg['atlas'][source]
            if f'{ax}:{ay}/0' not in atlas.props: raise ExportError(path,bg['line'],'Cella riferita a tile non dichiarata nell’atlante')
            image_data=images[texture]; w,h=bg['size']
            if (ax+1)*w>image_data[0] or (ay+1)*h>image_data[1]: raise ExportError(path,bg['line'],'Coordinate atlante fuori PNG')
            for ty in range(h//8):
                for tx in range(w//8):
                    mx,my=x*w//8+tx,y*h//8+ty
                    if not 0<=mx<32 or not 0<=my<32: raise ExportError(path,bg['line'],'TileMap oltre 256×256 o con coordinate negative')
                    tile=tiles(image_data,bg_colors,bpp,(ax*w+tx*8,ay*h+ty*8,8,8))
                    if tile not in dedup: dedup[tile]=len(dedup); bg_tiles.extend(tile)
                    screen[my*32+mx]=dedup[tile]
        output.append(c_array('bg_map_'+str(i),screen,'unsigned short'))
        bg_rows.append('{'+f'{bg["node"]},{28+i},bg_map_{i}'+'}')
    if len(bg_tiles)>32768 or len(dedup)>1024: raise ExportError(path,1,'Tiles BG oltre 32 KiB/1024 indici')
    output.append(c_array('background_tiles',bg_tiles))
    output.append('const unsigned background_tiles_size='+str(len(bg_tiles))+';\n')
    output.append('const Background backgrounds[] = {'+(','.join(bg_rows) or '{0}')+'};\n')
    output.append(c_array('object_palette',(obj_palette+[0]*256)[:256],'unsigned short'))
    output.append(c_array('background_palette',(bg_palette+[0]*256)[:256],'unsigned short'))
    output.append('const Shape shapes[] = {'+(','.join('{'+','.join(map(str,s))+'}' for s in shape_list) or '{0}')+'};\n')
    rows=[]
    for n in nodes:
        p=n['section'].props
        rows.append('{{'+','.join(map(str,n['pos']))+'},{0,0},{0,0},'+','.join(map(str,[n['parent'],1 if n['type']=='CharacterBody2D' else 2 if n['type']=='StaticBody2D' else 0,n['visible'],p.get('frame',0),int(p.get('flip_h',False)),int(p.get('flip_v',False)),0,n['shape'],n['sprite']]))+'}')
    output.append('GbaNode nodes[] = {'+','.join(rows)+'};\n')
    output.append(f'const int node_count={len(nodes)}, shape_count={len(shape_list)}, sprite_count={len(sprite_list)}, background_count={len(bg_list)}, gba_bpp={bpp}, has_audio={int(bool(sounds))};\n')
    output.extend(d+'\n' for d in declarations)
    for index,funcs in functions:
        for name,body in funcs.items():
            output.append(f'static void node_{index}{name}(float delta) {{\n(void)delta;\n'+body+'\n}\n')
    for callback in ('_ready','_physics_process'):
        calls=''.join(f'node_{index}{callback}({"delta" if callback=="_physics_process" else "0"});\n' for index,f in functions if callback in f)
        output.append(('void scripts_ready(void) {\n' if callback=='_ready' else 'void scripts_tick(float delta) {\n(void)delta;\n')+calls+'}\n')
    output.append('void sounds_ready(void) {\n'+''.join(f'play_sound({i},{vol});\n' for i,(_,vol,autoplay) in enumerate(sounds) if autoplay)+'}\n')
    total_audio=0
    for i,(source,_,_) in enumerate(sounds):
        total_audio+=convert_wav(source,out/f'sample_{i:03d}.wav')
    if total_audio+sum(len(s.encode()) for s in output)//3>32*1024*1024: raise ExportError(path,1,'Stima dati oltre ROM 32 MiB')
    if not sounds: output.append(c_array('soundbank',b'\0\0\0\0'))
    (out/'generated.c').write_text(''.join(output),encoding='utf-8',newline='\n')
    here=Path(__file__).parent
    for name in ('runtime.c','runtime.h'): shutil.copyfile(here/name,out/name)
    return {'nodes':len(nodes),'sprites':len(sprite_list),'backgrounds':len(bg_list),'collisions':len(shape_list),
            'object_vram_bytes':obj_vram,'background_vram_bytes':len(bg_tiles)+len(bg_list)*2048,
            'audio_bytes':total_audio,'sounds':len(sounds),'bpp':bpp,
            'node_paths':{n['path']:n['index'] for n in nodes},'source_scene':str(path).replace('\\','/')}
