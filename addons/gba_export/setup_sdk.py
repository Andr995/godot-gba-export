"""Installazione locale opzionale: SDK ufficiale devkitPro (Linux/WSL) e core mGBA.

Nessun asset di gioco viene scaricato. I blob OCI vengono verificati tramite SHA256.
Eseguire dalla radice: python addons/gba_export/setup_sdk.py
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import shutil
import tarfile
import urllib.request
import zipfile

BASE = Path('tools/gba')
REGISTRY = 'https://registry-1.docker.io/v2/devkitpro/devkitarm'
# Manifest ufficiale amd64, fissato il 3 novembre 2026; non segue latest.
MANIFEST = 'sha256:15b79ce75822c289538d8153da5fa7aafe5e6adc32ad8a575a197beca0f0761b'
MGBA_URL = 'https://buildbot.libretro.com/nightly/windows/x86_64/latest/mgba_libretro.dll.zip'
MGBA_SHA256 = 'ada02eae2dd0146d1d4c114c0dbe4b2dc57b29a8e21610e68cff161273fed869'


def request(url, token=None):
    headers = {'User-Agent': 'Godot-GBA-local-build/1.0'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
        headers['Accept'] = 'application/vnd.oci.image.manifest.v1+json'
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-only', action='store_true', help='Installa solo la SDK, senza scaricare il core mGBA Windows fissato')
    args = parser.parse_args()
    if platform.machine().lower() not in ('amd64','x86_64'):
        raise RuntimeError('Setup locale disponibile per host x86_64; usare una propria installazione DEVKITPRO su altre architetture.')
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / '.gdignore').touch()
    cache = BASE / 'cache'
    cache.mkdir(parents=True, exist_ok=True)
    with request('https://auth.docker.io/token?service=registry.docker.io&scope=repository:devkitpro/devkitarm:pull') as response:
        token = json.load(response)['token']
    with request(REGISTRY + '/manifests/' + MANIFEST, token) as response:
        raw = response.read()
    if hashlib.sha256(raw).hexdigest() != MANIFEST.split(':')[1]:
        raise RuntimeError('Digest manifest OCI errato')
    manifest = json.loads(raw)
    (cache / 'manifest.json').write_bytes(raw)
    sdk = BASE / 'sdk'
    sdk.mkdir(exist_ok=True)
    for layer in manifest['layers']:
        digest = layer['digest'].split(':')[1]
        archive = cache / (digest + '.tar.gz')
        if not archive.exists():
            print('Download SDK layer:', layer['size'], 'byte', flush=True)
            with request(REGISTRY + '/blobs/' + layer['digest'], token) as response, archive.with_suffix('.partial').open('wb') as output:
                shutil.copyfileobj(response, output, 1024 * 1024)
            archive.with_suffix('.partial').replace(archive)
        with archive.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != digest:
                raise RuntimeError('SHA256 errato: ' + str(archive))
        links = []
        with tarfile.open(archive) as tar:
            for entry in tar:
                prefix = 'opt/devkitpro/'
                if not entry.name.startswith(prefix):
                    continue
                relative = Path(entry.name[len(prefix):])
                if not relative.parts or relative.parts[0] not in {'devkitARM', 'libtonc', 'maxmod', 'tools', 'libgba', 'examples', 'licenses'}:
                    continue
                target = sdk / relative
                if not target.resolve().is_relative_to(sdk.resolve()):
                    raise RuntimeError('Percorso archivio fuori dalla SDK')
                if entry.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif entry.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(entry) as source, target.open('wb') as output:
                        shutil.copyfileobj(source, output)
                    if os.name != 'nt':
                        target.chmod(entry.mode)
                elif entry.issym() or entry.islnk():
                    link = entry.linkname.lstrip('/')
                    source = (sdk / link[len(prefix):]) if link.startswith(prefix) else target.parent / entry.linkname
                    if not source.resolve().is_relative_to(sdk.resolve()):
                        raise RuntimeError('Link SDK fuori dalla cartella locale: ' + entry.name)
                    links.append((target, source))
        for target, source in links:
            if not source.exists():
                raise RuntimeError('Link SDK irrisolto: ' + str(source))
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copyfile(source, target)
        print('Layer verificato:', digest, flush=True)
    installation = {'sdk_manifest': MANIFEST, 'sdk': str(sdk), 'host': 'wsl' if os.name == 'nt' else 'linux'}
    if os.name == 'nt' and not args.sdk_only:
        archive = cache / 'mgba_libretro.dll.zip'
        if not archive.exists():
            with request(MGBA_URL) as response:
                archive.write_bytes(response.read())
        with zipfile.ZipFile(archive) as zipped:
            content = zipped.read('mgba_libretro.dll')
        if hashlib.sha256(content).hexdigest() != MGBA_SHA256:
            raise RuntimeError('Il nightly mGBA è cambiato: usare il core verificato nel cache oppure fornire GBA_MGBA_CORE. Nessun core diverso viene installato automaticamente.')
        destination = BASE / 'mgba'
        destination.mkdir(exist_ok=True)
        (destination / 'mgba_libretro.dll').write_bytes(content)
        installation.update(mgba_url=MGBA_URL, mgba_sha256=hashlib.sha256(content).hexdigest())
    (BASE / 'installed.json').write_text(json.dumps(installation, indent=2) + '\n', encoding='utf-8')
    print('SDK locale pronta. Su Windows richiede WSL Ubuntu con make; nessuna installazione globale.')


if __name__ == '__main__':
    main()
