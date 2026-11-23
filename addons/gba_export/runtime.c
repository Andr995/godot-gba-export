#include "runtime.h"

#define FRAME_DELTA (280896.0f / 16777216.0f)
static OBJ_ATTR object_buffer[128];
static int loaded_frame[128];
static unsigned keys, previous_keys;
/* Simboli osservabili dal test attraverso ELF; non usati per pilotare il gioco. */
volatile unsigned gba_frames, gba_fault, gba_keys;

int gba_key_held(unsigned key) { return (keys & key) != 0; }
int gba_key_hit(unsigned key) { return (keys & ~previous_keys & key) != 0; }
float gba_divf(float a, float b) { if (b == 0) { gba_fault=1; return 0; } return a/b; }
int gba_divi(int a, int b) { if (!b) { gba_fault=1; return 0; } return a/b; }
int gba_modi(int a, int b) { if (!b) { gba_fault=1; return 0; } return a%b; }

static Vec2 world_position(int index) {
    Vec2 result=nodes[index].position;
    for (int p=nodes[index].parent; p>=0; p=nodes[p].parent) result=gba_vec_add(result,nodes[p].position);
    return result;
}

static int node_visible(int index) {
    for (int p=index; p>=0; p=nodes[p].parent) if (!nodes[p].visible) return 0;
    return 1;
}

void move_body(int index) {
    GbaNode *node=&nodes[index];
    if (node->shape < 0) { gba_fault=2; return; }
    const Shape *body=&shapes[node->shape];
    Vec2 start=world_position(index);
    float x=start.x+body->x-body->w/2, y=start.y+body->y-body->h/2;
    float dx=node->velocity.x*FRAME_DELTA, dy=node->velocity.y*FRAME_DELTA;
    if (!isfinite(dx) || !isfinite(dy) || fabsf(dx)>128 || fabsf(dy)>128) { gba_fault=3; return; }
    node->grounded=0;
    float target=x+dx;
    for (int i=0;i<shape_count;i++) {
        const Shape *s=&shapes[i];
        if (nodes[s->node].type!=2 || s->one_way || !(body->mask&s->layer)) continue;
        Vec2 pos=world_position(s->node);
        float sx=pos.x+s->x-s->w/2, sy=pos.y+s->y-s->h/2;
        if (y+body->h<=sy || y>=sy+s->h) continue;
        if (dx>0 && x+body->w<=sx+0.01f && target+body->w>sx) { target=sx-body->w; node->velocity.x=0; }
        if (dx<0 && x>=sx+s->w-0.01f && target<sx+s->w) { target=sx+s->w; node->velocity.x=0; }
    }
    x=target;
    target=y+dy;
    for (int i=0;i<shape_count;i++) {
        const Shape *s=&shapes[i];
        if (nodes[s->node].type!=2 || !(body->mask&s->layer)) continue;
        Vec2 pos=world_position(s->node);
        float sx=pos.x+s->x-s->w/2, sy=pos.y+s->y-s->h/2;
        if (x+body->w<=sx || x>=sx+s->w) continue;
        if (dy>=0 && y+body->h<=sy+0.05f && target+body->h>=sy) {
            target=sy-body->h; node->velocity.y=0; node->grounded=1;
        }
        if (dy<0 && !s->one_way && y>=sy+s->h-0.01f && target<sy+s->h) {
            target=sy+s->h; node->velocity.y=0;
        }
    }
    node->position.x+=x-(start.x+body->x-body->w/2);
    node->position.y+=target-y;
}

void play_sound(int sample, int volume) {
    if (!has_audio) { gba_fault=4; return; }
    mm_sfxhand handle=mmEffect((mm_word)sample);
    mmEffectVolume(handle,(mm_word)volume);
}

static void render(void) {
    for (int i=0;i<sprite_count;i++) {
        const Sprite *sprite=&sprites[i];
        GbaNode *node=&nodes[sprite->node];
        Vec2 pos=world_position(sprite->node);
        int x=(int)floorf(pos.x+sprite->offset_x-(sprite->centered?sprite->frame_w/2.0f:0));
        int y=(int)floorf(pos.y+sprite->offset_y-(sprite->centered?sprite->frame_h/2.0f:0));
        if (node->frame<0 || node->frame>=sprite->frames) { gba_fault=5; obj_hide(&object_buffer[i]); continue; }
        if (!node_visible(sprite->node) || x>=240 || y>=160 || x+sprite->frame_w<=0 || y+sprite->frame_h<=0) {
            obj_hide(&object_buffer[i]); continue;
        }
        if (loaded_frame[i]!=node->frame) {
            memcpy32((void*)(MEM_VRAM_OBJ+sprite->tile*32),sprite->pixels+node->frame*sprite->bytes,sprite->bytes/4);
            loaded_frame[i]=node->frame;
        }
        /* Padding trasparente: correzione origine quando il frame non riempie l'OBJ. */
        if (node->flip_h) x-=sprite->w-sprite->frame_w;
        if (node->flip_v) y-=sprite->h-sprite->frame_h;
        obj_set_attr(&object_buffer[i], (y&255)|(sprite->shape<<14)|(gba_bpp==8?ATTR0_8BPP:0),
            (x&511)|(sprite->size<<14)|(node->flip_h?ATTR1_HFLIP:0)|(node->flip_v?ATTR1_VFLIP:0), sprite->tile);
    }
    oam_copy(oam_mem,object_buffer,128);
    for (int i=0;i<background_count;i++) {
        if (node_visible(backgrounds[i].node)) REG_DISPCNT|=(1<<(8+i));
        else REG_DISPCNT&=~(1<<(8+i));
        Vec2 pos=world_position(backgrounds[i].node);
        REG_BG_OFS[i].x=(unsigned short)(-(int)pos.x);
        REG_BG_OFS[i].y=(unsigned short)(-(int)pos.y);
    }
}

int main(void) {
    irq_init(NULL);
    if (has_audio) {
        mmInitDefault((mm_addr)soundbank,8);
        irq_add(II_VBLANK,mmVBlank);
    } else irq_add(II_VBLANK,NULL);
    REG_DISPCNT=DCNT_MODE0|DCNT_OBJ|DCNT_OBJ_1D;
    memcpy16(pal_obj_mem,object_palette,256);
    memcpy16(pal_bg_mem,background_palette,256);
    if (background_tiles_size) memcpy32((void*)MEM_VRAM,background_tiles,background_tiles_size/4);
    for (int i=0;i<background_count;i++) {
        memcpy16(&se_mem[backgrounds[i].screenblock][0],backgrounds[i].map,1024);
        REG_BGCNT[i]=(unsigned short)(BG_CBB(0)|BG_SBB(backgrounds[i].screenblock)|(gba_bpp==8?BG_8BPP:0)|BG_PRIO(1));
        REG_DISPCNT|=(1<<(8+i));
    }
    oam_init(object_buffer,128);
    for (int i=0;i<128;i++) loaded_frame[i]=-1;
    scripts_ready();
    sounds_ready();
    for (;;) {
        previous_keys=keys;
        keys=(~REG_KEYINPUT)&1023;
        gba_keys=keys;
        scripts_tick(FRAME_DELTA);
        if (has_audio) mmFrame();
        VBlankIntrWait();
        render();
        gba_frames++;
        if (gba_fault) { pal_bg_mem[0]=RGB15(31,0,31); for (;;) VBlankIntrWait(); }
    }
}
