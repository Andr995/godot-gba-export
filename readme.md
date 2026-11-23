# GBA Export — modulo da integrare in Godot

**Questa cartella contiene esclusivamente il plugin generico per compilare un sottoinsieme di giochi 2D Godot 4 in ROM Game Boy Advance.** Copiare `addons/gba_export/` nel proprio progetto, preparare le dipendenze, abilitare il plugin ed eseguire **Project > Tools > Build GBA**.

Non sono inclusi un gioco, una demo, scene, sprite, audio, livelli, salvataggi, ROM o backend applicativi specifici. Non è un progetto Godot da avviare: non contiene `project.godot`. Il codice C presente è il runtime generico del modulo.

Il modulo traduce un sottoinsieme documentato di scene e GDScript. Non converte automaticamente qualsiasi progetto Godot: le funzionalità fuori contratto vengono rifiutate con diagnostica, e i giochi complessi richiedono un adattamento o un port dedicato.

## Indice

- [Contenuto del modulo](#contenuto-del-modulo)
- [Installazione nel proprio progetto](#installazione-nel-proprio-progetto)
- [Requisiti e preparazione della SDK](#requisiti-e-preparazione-della-sdk)
- [Uso dall’editor](#uso-dalleditor)
- [Uso da terminale](#uso-da-terminale)
- [Scene e nodi supportati](#scene-e-nodi-supportati)
- [GDScript supportato](#gdscript-supportato)
- [Input e collisioni](#input-e-collisioni)
- [Conversione della grafica](#conversione-della-grafica)
- [Conversione audio](#conversione-audio)
- [Limiti hardware](#limiti-hardware)
- [Output e gestione degli errori](#output-e-gestione-degli-errori)
- [Verifica della ROM](#verifica-della-rom)
- [Problemi frequenti](#problemi-frequenti)
- [Pubblicazione su GitHub](#pubblicazione-su-github)
- [Licenza e componenti esterni](#licenza-e-componenti-esterni)

## Contenuto del modulo

```text
modulo_per_github/
├── readme.md                  Guida completa all'integrazione
├── LICENSE                    Licenza del codice originale
├── VERIFICA.md                Esito delle verifiche della distribuzione
├── manifest.json              SHA-256 dei file consegnati
├── .gitignore                 Esclusione cache e dipendenze locali
├── .gitattributes             Terminatori di riga riproducibili
├── .gdignore                  Isolamento di questa cartella nel progetto ospite
└── addons/
    └── gba_export/
        ├── plugin.cfg         Identità del plugin
        ├── plugin.gd          Menu, thread e pannello log dell'editor
        ├── plugin.gd.uid      Identificatore dello script editor
        ├── export_gba.py      Driver CLI, make e controlli ROM/ELF
        ├── setup_sdk.py       Setup opzionale delle dipendenze locali
        ├── scene.py           Parser delle scene TSCN
        ├── gdscript.py        Compilatore del sottoinsieme numerico
        ├── compiler.py        Generazione C da nodi e risorse
        ├── assets.py          PNG, palette, tile e WAV
        ├── runtime.c          Implementazione generica C/libtonc
        ├── runtime.h          Strutture e API del runtime
        ├── README.md          Istruzioni sintetiche in dieci righe
        └── .gitignore         Esclusione cache Python
```

È un `EditorPlugin`: non richiede di ricompilare Godot. Non è un export template ufficiale, un modulo C++ del motore o una GDExtension. Il backend impiega C, devkitARM, **libtonc** e Maxmod; Butano non è richiesto.

I test di preparazione della distribuzione vengono eseguiti in un progetto temporaneo esterno alla cartella consegnata. Il pacchetto conserva soltanto il loro esito, senza includere una demo da distribuire accidentalmente insieme al modulo.

## Installazione nel proprio progetto

1. Aprire la cartella del proprio gioco, quella che contiene `project.godot`.
2. Copiare al suo interno `addons/gba_export/`, mantenendo esattamente questa struttura. Se esiste già una versione del plugin, conservarne una copia prima di sostituirla.
3. Installare Python 3.11+ e preparare la SDK come indicato sotto.
4. Aprire il proprio progetto con Godot 4 portable.
5. Entrare in **Project > Project Settings > Plugins** e abilitare **GBA Export**.
6. Salvare scene e script e verificare il contratto di compatibilità.
7. Eseguire **Project > Tools > Build GBA**.

La struttura finale deve essere:

```text
proprio_progetto/
├── project.godot              Il file già esistente del proprio gioco
├── scene_e_script_del_gioco/
└── addons/
    └── gba_export/
        ├── plugin.cfg
        ├── plugin.gd
        └── ...
```

Non copiare la cartella `modulo_per_github` dentro `addons`: copiare la sottocartella `gba_export`. Non copiare `.gdignore` dalla radice della distribuzione alla radice del gioco: quel file serve a nascondere la distribuzione al progetto che eventualmente la contiene. L'addon non ha un `.gdignore` proprio e deve restare visibile all'editor.

La guida ufficiale Godot descrive l'[installazione dei plugin](https://docs.godotengine.org/en/stable/tutorials/plugins/editor/installing_plugins.html). I nomi dei menu possono variare con la lingua dell'interfaccia.

L'abilitazione del plugin è una normale modifica alla configurazione dell'editor. La build legge i file salvati, genera output sotto `build/` e non riscrive scene, script o asset del gioco. Godot può comunque generare cache e metadati di importazione durante le proprie operazioni ordinarie.

## Requisiti e preparazione della SDK

| Componente | Necessità |
| --- | --- |
| Godot 4 portable | Menu editor e sviluppo; non richiesto dalla sola CLI |
| Python 3.11+ | Analisi, conversione e build anche quando avviate dall'editor |
| devkitARM | Compilatore e linker ARM7TDMI |
| libtonc | Accesso all'hardware GBA |
| Maxmod, `mmutil` | Mixer e generazione soundbank |
| `gbafix` | Finalizzazione dell'header della ROM |
| GNU make | Esecuzione del Makefile generato |
| mGBA | Verifica della ROM; non richiesto per la sola compilazione |

Il tooling Python usa soltanto la standard library: nessun `pip install`, Pillow o NumPy. Il giocatore non necessita di Python o Godot per eseguire la ROM. Il runtime non utilizza rete o telemetria.

Tutti i comandi della guida si eseguono **dalla radice del proprio gioco dopo aver copiato il plugin**. Su Linux usare `python3` quando `python` non identifica Python 3.11 o successivo. Godot portable può essere conservato in `tools/godot/`.

### SDK locale Linux oppure Windows con WSL

Il setup opzionale estrae una SDK Linux x86_64 da un'immagine OCI ufficiale devkitPro fissata nel codice. Verifica digest del manifest e SHA-256 dei layer. Non necessita del programma Docker e non avvia container.

```text
python addons/gba_export/setup_sdk.py --sdk-only
```

Scrive esclusivamente in `tools/gba/`: SDK, archivi scaricati e registro dell'installazione. Aggiunge `.gdignore` a questa directory per evitare l'importazione delle dipendenze da parte di Godot. Questa preparazione richiede rete e spazio per archivi ed estrazione; la successiva build usa file locali ed è offline.

Su Windows devono già esistere WSL, una distribuzione Ubuntu, Python 3 e GNU make al suo interno. Il setup non installa questi componenti di sistema. Controlli preliminari:

```powershell
python --version
wsl -l -v
wsl -d Ubuntu --exec python3 --version
wsl -d Ubuntu --exec make --version
```

Il driver Windows riconosce gli eseguibili Linux nella SDK locale e compila tramite WSL. Su Linux x86_64 li usa direttamente. Per un'altra distribuzione:

```powershell
$env:GBA_WSL_DISTRO = "Debian"
python addons/gba_export/export_gba.py
```

La distribuzione selezionata deve vedere il progetto e disporre di Python e make. Nel percorso Windows/WSL locale normalmente non si impostano `DEVKITPRO` e `DEVKITARM`: valori Windows ereditati dentro WSL possono impedire il rilevamento della SDK.

Il setup locale non fornisce una SDK macOS o ARM64. Per altri host serve una propria installazione compatibile. La configurazione effettivamente collaudata è riportata in [VERIFICA.md](VERIFICA.md).

### SDK devkitPro già installata

Il driver supporta una SDK nativa tramite `DEVKITPRO` e `DEVKITARM`; `make` o `mingw32-make` deve essere nel PATH. Verifica almeno:

```text
DEVKITPRO/devkitARM/bin/arm-none-eabi-gcc[.exe]
DEVKITPRO/libtonc/include/tonc.h
DEVKITPRO/libtonc/lib/libtonc.a
DEVKITPRO/libgba/include/maxmod.h
DEVKITPRO/libgba/lib/libmm.a
DEVKITPRO/tools/bin/mmutil[.exe]
DEVKITPRO/tools/bin/gbafix[.exe]
```

Se la propria SDK nativa è stata collocata in `tools/gba/sdk`:

```powershell
$env:DEVKITPRO = (Resolve-Path tools/gba/sdk).Path
$env:DEVKITARM = Join-Path $env:DEVKITPRO "devkitARM"
python addons/gba_export/export_gba.py
```

```sh
export DEVKITPRO="$PWD/tools/gba/sdk"
export DEVKITARM="$DEVKITPRO/devkitARM"
python3 addons/gba_export/export_gba.py
```

Su Windows questi esempi valgono per compilatori Windows `.exe`. Le variabili non trasformano una SDK Linux in una SDK Windows. Preferire SDK e progetto sullo stesso volume e percorsi semplici: il Makefile usa percorsi relativi e le unità Windows diverse non sono una configurazione collaudata.

Non aggiungere SDK, cache o librerie degli emulatori al repository del proprio gioco. Il `.gitignore` della distribuzione contiene le esclusioni utili; quando si copia il solo addon, aggiungere quelle necessarie al `.gitignore` già esistente del gioco.

### Setup opzionale del core mGBA

Senza `--sdk-only`, il setup tenta anche di scaricare su Windows x64 uno specifico core mGBA libretro. L'hash è fissato, mentre l'URL remoto è un nightly: se il contenuto cambia, il controllo fallisce intenzionalmente. La SDK può essere preparata separatamente con `--sdk-only`.

Quel core è una libreria per test automatici, non l'applicazione grafica. Il modulo non contiene un frontend di test universale e non avvia automaticamente mGBA. Per la prova manuale usare l'applicazione disponibile sulla [pagina ufficiale mGBA](https://mgba.io/downloads.html).

## Uso dall'editor

Il plugin registra il menu **Build GBA** e il pannello inferiore **GBA Export**. Non compila all'apertura del progetto: serve il comando esplicito.

La build legge la scena principale indicata in `project.godot`, controlla le risorse, genera C e dati, esegue `mmutil` e `make`, verifica header e budget e pubblica `build/gba/game.gba`.

Il lavoro viene eseguito in un thread; il pannello legge il log durante l'operazione. Non si avviano due build contemporanee dal plugin. Disabilitare il plugin o chiudere l'editor attende il worker; non è disponibile un pulsante di annullamento immediato. I comandi esterni hanno timeout.

Il menu usa 8bpp e `build/gba`. Le altre impostazioni sono disponibili dalla CLI. Le modifiche non salvate nell'editor non entrano nella ROM.

Per selezionare Python, impostare `GBA_PYTHON` prima di avviare Godot dallo stesso terminale:

```powershell
$env:GBA_PYTHON = (Get-Command python).Source
```

Il valore deve essere un eseguibile, non un comando con argomenti come `py -3.11`. Su Windows il default è `python`; sugli altri sistemi è `python3`. L'ambiente deve essere visibile al processo Godot già all'avvio.

## Uso da terminale

```text
python addons/gba_export/export_gba.py --help
python addons/gba_export/export_gba.py
python addons/gba_export/export_gba.py --analyze --out build/analysis
python addons/gba_export/export_gba.py --bpp 4 --out build/gba_4bpp
python addons/gba_export/export_gba.py --scene scenes/gba_main.tscn --out build/gba_scene
python addons/gba_export/export_gba.py --log build/gba/cli.log
```

| Opzione | Default | Significato |
| --- | --- | --- |
| `--project` | `.` | Directory del progetto; il driver la usa come directory corrente |
| `--scene` | Scena principale | Percorso filesystem di un `.tscn`, senza prefisso `res://` |
| `--out` | `build/gba` | Sottocartella di `build/` interna al progetto |
| `--bpp` | `8` | Profondità 4 oppure 8 bit per pixel |
| `--profile` | `strict` | Unico profilo presente: compilatore generico |
| `--analyze` | Disattivato | Valida e genera intermedi senza make né nuova ROM |
| `--log` | Console | File sotto `build/` per stdout e stderr |

La scena principale deve essere dichiarata con un percorso esplicito:

```ini
[application]
run/main_scene="res://main.tscn"
```

Gli identificatori `uid://...` come scena iniziale non sono supportati. `--scene` seleziona una scena diversa: la sua compilazione non prova che l'intero progetto sia stato convertito. Il compilatore non unisce tutte le scene di una directory e non segue cambi di scena dinamici.

`--analyze` prepara comunque la cartella di output: una ROM precedente presente lì viene spostata in `game.previous.gba`. Usare `--out build/analysis` per analizzare senza spostare la ROM destinata alla distribuzione.

L'analisi può passare anche se manca la SDK, segnalando tale assenza. `analysis_passed` non significa che il codice ARM sia stato compilato. Una build completa restituisce 0 su successo e normalmente 2 per errori di esportazione; controllare anche log e report.

L'opzione interna `--make-only` serve al passaggio Windows→WSL, non all'uso ordinario. Non esistono profili applicativi `auto`/`campaign` o un harness della campagna in questa distribuzione.

## Scene e nodi supportati

Scene testuali Godot 4 con albero statico, parent prima dei figli e risorse esplicite. Sono supportate traslazioni; rotazione, scala e trasformazioni affini generiche sono fuori contratto.

| Nodo | Proprietà specifiche riconosciute |
| --- | --- |
| `Node2D` | Proprietà comuni |
| `Sprite2D` | `texture`, `hframes`, `vframes`, `frame`, `flip_h`, `flip_v`, `centered`, `offset` |
| `CharacterBody2D` | `collision_layer`, `collision_mask`, `motion_mode` nei valori validati |
| `StaticBody2D` | `collision_layer`, `collision_mask` |
| `CollisionShape2D` | `shape` rettangolare, `one_way_collision` |
| `AudioStreamPlayer` | `stream`, `autoplay`, `volume_db` |
| `TileMapLayer` | `tile_set`, `tile_map_data`, `enabled` |

Le proprietà comuni sono `position`, `visible`, `z_index` e `script`. Un `z_index` non nullo è ammesso direttamente su Sprite2D. Proprietà o attributi non riconosciuti vengono rifiutati anche se Godot li serializza normalmente.

Risorse interne supportate: RectangleShape2D, TileSet e TileSetAtlasSource. PNG, WAV e script sono risorse esterne nei ruoli previsti. Non sono supportate risorse `.tres` esterne, scene ereditate/istanziate, gruppi, segnali o autoload.

Non sono compresi nodi 3D, Control, Label, Button, Camera2D, AnimatedSprite2D, AnimationPlayer, Area2D, RigidBody2D, particelle, shader, navigazione, filesystem, networking o caricamento dinamico. Il fatto che un gioco sia 2D non garantisce la compatibilità.

### TileMapLayer

- Dati `tile_map_data` nativi formato 0; TileSet e atlas come sub-resource.
- Tile logiche 8×8, 16×16 o 32×32, convertite in tile hardware 8×8.
- Ciascun BG ha area massima 256×256 pixel; coordinate non negative.
- Fino a quattro BG con tile deduplicate.
- Nessun terrain, tile animata, alternativa, flip o trasposizione del TileSet.
- Collisioni del TileSet non convertite: usare StaticBody2D con shape rettangolari separate.
- TileMapLayer inizialmente invisibile o disabilitato rifiutato.
- Il vecchio nodo TileMap viene rifiutato.

Non c'è una camera o uno scorrimento automatico per livelli più grandi.

## GDScript supportato

Il codice diventa C, senza VM Godot sulla console. I tipi sono `float`, `int`, `bool` e `Vector2`; le variabili devono essere tipizzate e inizializzate.

| Area | Supporto |
| --- | --- |
| Callback | `_ready()` e `_physics_process(delta: float)` |
| Stato | Variabili e costanti numeriche/booleane/Vector2 |
| Controllo | Assegnamenti, if/elif/else, return nei casi gestiti |
| Espressioni | Aritmetica scalare, confronti, logica booleana, parte dell'aritmetica Vector2 |
| Funzioni | Conversioni numeriche, minf/maxf/clampf/absf/move_toward |
| Accesso nodi | `$Figlio` statico, position/visible e proprietà sprite supportate |
| Movimento | move_and_slide, is_on_floor nel modello AABB del runtime |
| Audio | `.play()` su AudioStreamPlayer statico |

Esempio per un CharacterBody2D già provvisto di CollisionShape2D rettangolare:

```gdscript
extends CharacterBody2D

const SPEED: float = 90.0

func _physics_process(delta: float) -> void:
    velocity.x = Input.get_axis("left", "right") * SPEED
    velocity.y = minf(velocity.y + 650.0 * delta, 350.0)
    if is_on_floor() and Input.is_action_just_pressed("jump"):
        velocity.y = -240.0
    move_and_slide()
```

Il frammento illustra il contratto e non costituisce un gioco incluso nel pacchetto. Per provarlo in Godot, configurare anche le azioni nella Input Map del proprio progetto.

Non sono supportati Dictionary/Array, Variant dinamici, stringhe applicative, cicli, funzioni applicative arbitrarie, segnali, Callable, coroutine/await, allocazione di nodi o caricamento dinamico. Il comportamento preciso degli operatori è definito da [gdscript.py](addons/gba_export/gdscript.py).

Gli interi C hanno 32 bit e i float sono software: compatibilità sintattica non significa prestazioni o comportamento numerico identici a Godot. Evitare overflow; non tutti i valori runtime sono verificabili staticamente.

## Input e collisioni

Il GBA usa una mappa fissa di nomi di azione, non una conversione dei binding fisici tastiera/gamepad di Godot.

| Pulsante | Nomi riconosciuti |
| --- | --- |
| A | jump, p1_jump, ui_accept |
| B | attack, p1_attack |
| Select | select |
| Start | pause, start, ui_cancel |
| Destra | right, p1_right, ui_right |
| Sinistra | left, p1_left, ui_left |
| Su | up, ui_up |
| Giù | down, ui_down |
| R | switch, p1_switch, r |
| L | l |

API riconosciute: `Input.get_axis`, `Input.is_action_pressed`, `Input.is_action_just_pressed`, con nomi letterali supportati. Una mappatura non crea il gameplay: per esempio B attacca solo se lo script implementa l'attacco.

La fisica supporta un rettangolo per corpo, collisioni AABB, layer/mask e piattaforme one-way. `move_and_slide()` risolve separatamente gli assi con attraversamento dei bordi. `is_on_floor()` osserva il risultato del precedente aggiornamento.

Niente pendenze, collisioni tra personaggi, corpi mobili generici, snapping o recupero di sovrapposizioni. Le shape non sono modificabili a runtime. Posizionare un corpo già incastrato non garantisce una risoluzione come in Godot.

Il modulo generico non implementa salvataggi SRAM, cooperativa o link cable. Per questi sistemi serve una progettazione e un'implementazione C aggiuntiva.

## Conversione della grafica

Il decoder accetta PNG RGB/RGBA/grigio 8 bit e PNG indicizzati 1/2/4/8 bit, non interlacciati. Controlla firma, CRC, filtri, dimensioni e integrità dei dati, entro 4 megapixel e 4096 pixel per lato.

La conversione produce RGB555, con 5 bit per canale. Sono impiegate due palette globali, una OBJ e una BG:

| Modalità | Colori opachi massimi per palette | Trasparenza |
| --- | --- | --- |
| 4bpp | 15 | Indice 0 riservato |
| 8bpp | 255 | Indice 0 riservato |

Il conteggio avviene dopo RGB555: colori simili possono coincidere. Non si usano automaticamente tutte le palette hardware 4bpp per aggirare il limite globale. Se la palette eccede il budget, la conversione fallisce; non elimina colori per far passare la build.

Alpha parziale rifiutato: preparare asset GBA con alpha 0 o 255. La trasparenza non viene convertita silenziosamente in opacità binaria. Il colore zero BG deriva dal colore di cancellazione del progetto.

Sprite con atlanti supportano hframes/vframes/frame, centratura, offset, flip e visibilità ereditata. I frame ricevono padding fino a una dimensione OBJ legale, massimo 64×64. L'atlante resta in ROM; solo il frame attivo viene caricato in VRAM.

Il viewport target è 240×160 a coordinate 1:1. Non vengono ridimensionati automaticamente asset HD, UI o layout desktop. Una texture molto grande non diventa un grande sprite GBA: deve essere preparata o suddivisa con logica appropriata.

## Conversione audio

Input: WAV PCM8/PCM16 mono o stereo. Output intermedio: PCM8 mono a 11025 Hz con media per intervallo durante il ricampionamento. `mmutil` genera davvero il soundbank Maxmod collegato alla ROM.

Gli originali restano invariati. Playback one-shot, mixer fino a otto voci, volume da -80 a 0 dB. Nessun loop/playlist automatico, bus o effetto audio Godot. MP3, Ogg, FLAC e stream compressi non sono supportati.

Il driver non taglia la durata per rispettare i 32 MiB. Se l'audio occupa troppo, occorre preparare esplicitamente risorse adatte. La presenza di un soundbank non prova la qualità percepita: ascoltare il risultato oltre ai controlli automatici dei campioni.

## Limiti hardware

Target ARM7TDMI circa 16,78 MHz, 240×160, circa 59,73 Hz, 32 KiB IWRAM, 256 KiB EWRAM.

| Risorsa | Limite controllato |
| --- | --- |
| Nodi statici | 256 |
| Sprite OAM | 128 |
| Shape | 128 |
| BG | 4 |
| ROM | 32 MiB |
| Tile BG | 32 KiB, massimo 1024 indici |
| Mappe | Quattro screenblock, 256×256 per BG |
| Upload OBJ per VBlank | 16 KiB |
| Occupazione ELF IWRAM | 28 KiB, lasciando 4 KiB per stack/IRQ |
| Occupazione statica EWRAM | 192 KiB, lasciando 64 KiB per heap/audio/stack |

Controlli prudenziali coprono anche il carico sprite per scanline. I limiti non provano FPS costanti, uso massimo effettivo dello stack o stabilità per ore. Ogni gioco richiede un collaudo del carico reale; il GBA non esegue il motore Godot.

Il runtime espone simboli utili ai verificatori ELF: `gba_frames`, `gba_keys`, `gba_fault` e i nodi. In condizioni rilevate come invalide la simulazione si arresta con sfondo magenta:

| Fault | Condizione |
| --- | --- |
| 1 | Divisione/modulo per zero |
| 2 | Movimento senza shape |
| 3 | Spostamento non finito o oltre 128 pixel per asse/aggiornamento |
| 4 | Audio richiesto senza inizializzazione audio |
| 5 | Frame oltre i limiti dell'atlante |

Questi controlli non rilevano qualsiasi possibile errore applicativo.

## Output e gestione degli errori

```text
build/gba/
├── game.gba             Nuova ROM dopo tutti i controlli
├── game.previous.gba    Eventuale risultato precedente
├── report.json          Stato, diagnostiche, memoria e SHA-256
├── symbols.json         Simboli ELF
├── editor.log           Log del comando nell'editor
├── .gba_export_output   Identifica una cartella gestita dal driver
└── work/                C, Makefile, WAV convertiti, soundbank, ELF e map
```

Prima di un nuovo tentativo, una ROM precedente viene rinominata. Se la build fallisce, non viene presentata come appena riuscita. Gli intermedi in `work/` possono essere rimasti da un tentativo precedente: leggere sempre il report e usare solo la ROM verificata.

`report.json` distingue `built`, `analysis_passed` e `failed`. Su successo registra SHA-256, dimensione, memoria e toolchain. Errori iniziali di argomenti o accesso alla directory possono precedere il report: controllare anche il codice di uscita e il log.

| Codice | Significato |
| --- | --- |
| GBA001 | Contratto scene, asset o budget violato |
| GDS001 | Costrutto GDScript non convertibile |
| TOOL001 | SDK/componente mancante o processo non avviabile |
| TOOL002 | Timeout del processo |
| TOOL003 | Comando esterno terminato con errore |
| AUDIT | Indicazione aggiuntiva dell'inventario preliminare |
| INTERNAL | Eccezione inattesa intercettata |

Esempio: `scripts/player.gd:17: error GDS001: Identificatore non convertibile: inventory`.

Per errori sintattici viene indicata la riga del sorgente. Errori di SDK, palette aggregata, asset binari o budget usano una posizione sintetica, ad esempio `assets:1` o `project.godot:1`. GCC può riferirsi a una riga del C generato.

L'inventario preliminare visita convenzionalmente `scripts/` e `assets/`; non è una scansione semantica esaustiva del progetto. La validazione effettiva segue la scena selezionata e le risorse che essa riferisce staticamente.

## Verifica della ROM

Una build riuscita prova compilazione, header e limiti controllati; non certifica tutta la logica. Aprire la ROM in mGBA e controllare almeno avvio, sprite e BG, input, collisioni, audio e condizioni di vittoria/sconfitta previste dal proprio gioco.

Per test automatici si può usare un core mGBA libretro con un proprio frontend, osservando framebuffer, audio e simboli ELF. Questo pacchetto non include un test che conosca le scene di qualsiasi gioco: tali verifiche devono essere sviluppate per il progetto destinatario.

Le verifiche effettive del modulo consegnato sono descritte in [VERIFICA.md](VERIFICA.md). Il progetto sintetico usato nei test rimane fuori dalla distribuzione. Test automatici e compilazione non equivalgono a un playtest umano completo o a una prova su console/flashcart fisica.

## Problemi frequenti

| Sintomo | Controllo o soluzione |
| --- | --- |
| Il menu non compare | Verificare addons/gba_export/plugin.cfg e abilitazione del plugin |
| Python non disponibile | Controllare versione, PATH e GBA_PYTHON ereditato da Godot |
| SDK mancante | Eseguire il setup locale oppure configurare SDK nativa e variabili |
| make non trovato | Installarlo nell'host che compila; con WSL deve esistere nella distro |
| WSL non avvia Ubuntu | Verificare distro installata e GBA_WSL_DISTRO |
| Hash mGBA diverso | Usare --sdk-only e preparare separatamente il proprio ambiente di test |
| Scena principale UID | Usare un percorso res://...tscn esplicito |
| Dictionary/Control/shader rifiutato | Fuori contratto; implementare un adattamento o port dedicato |
| PNG con alpha parziale | Preparare esplicitamente una copia dell'asset con alpha binario |
| Troppi colori 4bpp | Preparare una palette ridotta oppure usare 8bpp |
| Sprite troppo grande | Ridisegnare o suddividere con una logica compatibile |
| Mancano le collisioni TileSet | Usare corpi statici rettangolari separati |
| ROM oltre 32 MiB | Valutare soprattutto soundbank e atlanti; nessun taglio automatico |
| Esiste solo game.previous.gba | Controllare l'ultimo report: analisi o build fallita |
| Input diverso dalla versione PC | Usare i nomi di azione della tabella fissa GBA |
| Schermo magenta | Leggere gba_fault e controllare movimento, frame e operazioni numeriche |
| --profile campaign non accettato | Questo pacchetto contiene solo il modulo generico strict |

Non eliminare un errore semplicemente facendo ignorare al parser una proprietà: bisogna implementarne il significato. Accettare la sintassi senza comportamento equivalente produrrebbe una conversione incompleta.

Per aggiungere una feature: definire il contratto, aggiornare parser e generazione C, implementare il runtime, verificare un caso negativo e un caso reale in emulatore e aggiornare la documentazione.

## Pubblicazione su GitHub

Caricare **il contenuto di `modulo_per_github/`** come radice del repository. Il README, la licenza, gli avvisi e `addons/gba_export/` descrivono un modulo installabile, senza il gioco originale.

Non caricare la cartella del progetto di provenienza, SDK, ROM, cache o salvataggi. Nessun account, remote o token è preimpostato. La preparazione della cartella non pubblica automaticamente nulla.

Con Git, dalla cartella `modulo_per_github`:

```text
git init
git add .
git status --short
git commit -m "Add standalone Godot GBA export plugin"
git branch -M main
```

Creare il repository nell'account desiderato e usare i comandi remote/push forniti da GitHub per il suo indirizzo effettivo. Con un caricamento web includere anche i file nascosti. Per integrare il modulo nel gioco, resta sufficiente copiare `addons/gba_export/`.

`manifest.json` registra i byte dei sorgenti di questa consegna; modifiche successive richiedono un aggiornamento del manifest. La configurazione Git usa LF per evitare alterazioni dei byte dovute ai terminatori di riga.

## Licenza e componenti esterni

Il codice originale distribuito segue [The Unlicense](LICENSE), mantenendo la licenza del progetto di provenienza. Nessun asset di quel gioco è incluso o concesso implicitamente da questa distribuzione.

Godot, Python, devkitARM, libtonc, Maxmod e mGBA sono componenti esterni con proprie licenze. I loro binari non sono incorporati nel modulo. Le condizioni delle dipendenze effettivamente scaricate o collegate non sono sostituite dalla licenza del plugin.

| Componente | Uso e riferimento |
| --- | --- |
| Godot | Editor ospite: [godotengine/godot](https://github.com/godotengine/godot) |
| Python | Tooling: [python/cpython](https://github.com/python/cpython) |
| devkitPro/devkitARM | Toolchain: [devkitPro](https://github.com/devkitPro) |
| libtonc | Runtime hardware: [devkitPro/libtonc](https://github.com/devkitPro/libtonc) |
| Maxmod | Mixer e soundbank: [devkitPro/maxmod](https://github.com/devkitPro/maxmod) |
| mGBA | Collaudo: [mgba-emu/mgba](https://github.com/mgba-emu/mgba) |

La ROM compilata collega librerie della SDK; chi la distribuisce deve conservare gli avvisi applicabili alle versioni utilizzate. Godot, Python e mGBA non vengono incorporati nella ROM. Per i test sintetici del modulo non è richiesto un BIOS proprietario o una ROM commerciale.
