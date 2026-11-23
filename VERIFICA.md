# Verifica del solo modulo — 23 novembre 2026

Distribuzione collaudata senza backend applicativo, dati o sorgenti del gioco originale. Il plugin è stato copiato in un progetto sintetico temporaneo esterno a `modulo_per_github`; tale progetto non viene distribuito.

| Controllo | Esito |
| --- | --- |
| Separazione del modulo | Nessuna scena, asset, ROM, eseguibile o codice della campagna nel pacchetto |
| Dipendenze Python | Nessun import del backend del gioco; sintassi valida |
| CLI | Unico profilo `strict`; richiesta `campaign` rifiutata con codice 2 |
| Contratti generici | 13 test PASS: PNG, palette, tile, script, diagnostica, SDK mancante, OAM, output e percorsi |
| Compilazione 8bpp | devkitARM/make reali, PASS; ROM sintetica 35.920 byte |
| Compilazione 4bpp | devkitARM/make reali, PASS; ROM sintetica 24.192 byte |
| mGBA 8bpp | 912 frame video, 902 aggiornamenti; boot, rendering, input, salto/doppio salto, pavimento, piattaforma one-way, cambio sprite e audio PASS |
| mGBA 4bpp | Colori, trasparenza e movimento PASS |
| Editor negativo | Diagnostica attesa, pannello, comando asincrono e cleanup PASS |
| Editor positivo | Build GBA produce una ROM identica byte per byte alla CLI |
| Import Godot | Progetto sintetico e progetto originale importati headless senza errori/warning |
| Originali | 755 file del gioco e dell'addon originale invariati per SHA-256 |
| Distribuzione | Contenuto limitato da elenco esplicito, manifest SHA-256 e confronto byte per byte dello ZIP |

Ambiente di esecuzione: Windows x64, WSL Ubuntu, devkitARM GCC 16.1.0, Godot 4.7.2 portable e core mGBA libretro `0.11-212-7a12d6d`.

SHA-256 della ROM sintetica 8bpp: `5b571babf6fbdf172e006dcb823a3d8557cb7bc48d0d8318cbed363f5153a9e7`.

SHA-256 della ROM sintetica 4bpp: `4abec3c551c668535322fe49fdc2c6cc7d6caa119a04321fdce2e945d9ca5f2b`.

Core mGBA SHA-256: `ada02eae2dd0146d1d4c114c0dbe4b2dc57b29a8e21610e68cff161273fed869`.

Le ROM riportate sono esclusivamente artefatti di collaudo e non sono presenti nella cartella del modulo. I test osservano framebuffer, input, audio e simboli ELF senza pilotare le posizioni del personaggio scrivendo nella RAM emulata.

Sono state riutilizzate dipendenze di sviluppo locali. Per `setup_sdk.py` sono stati verificati il caricamento e le opzioni CLI; i download remoti non sono stati ripetuti. Nessuna pubblicazione GitHub, prova su hardware GBA/flashcart, test macOS o certificazione di tutte le configurazioni native. Il collaudo sintetico non certifica giochi arbitrari o un playtest umano prolungato.

La funzionalità supportata e le istruzioni di integrazione sono nel [README dettagliato](readme.md).
