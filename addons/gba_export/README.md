1. Copiare addons/gba_export/ nella cartella addons/ del proprio progetto Godot 4.
2. Documentazione completa: readme.md nella radice della distribuzione modulo_per_github.
3. Richiede Python 3.11+, devkitARM, libtonc, Maxmod, mmutil, gbafix e GNU make.
4. SDK locale Linux/WSL: python addons/gba_export/setup_sdk.py --sdk-only dalla radice del gioco.
5. Abilitare GBA Export in Project > Project Settings > Plugins; salvare scene e script.
6. Compilare su richiesta da Project > Tools > Build GBA; log nel pannello GBA Export.
7. CLI: python addons/gba_export/export_gba.py; analisi: --analyze --out build/analysis.
8. Output: build/gba/game.gba, report.json, editor.log e sorgenti C/ELF in work/.
9. Sottoinsieme 2D statico e GDScript numerico; feature non supportate producono errori.
10. Solo modulo generico: nessun gioco, demo, asset, ROM o backend applicativo incluso.
