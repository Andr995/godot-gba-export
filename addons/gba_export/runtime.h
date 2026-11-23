#ifndef GBA_EXPORT_RUNTIME_H
#define GBA_EXPORT_RUNTIME_H
#include <tonc.h>
#include <maxmod.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

typedef struct { float x, y; } Vec2;
typedef struct {
    Vec2 position, velocity, world;
    int parent, type, visible, frame, flip_h, flip_v, grounded;
    int shape, sprite;
} GbaNode;
typedef struct { int node; float x, y, w, h; unsigned layer, mask; int one_way; } Shape;
typedef struct {
    int node, w, h, frame_w, frame_h, frames, shape, size, tile, bytes, centered;
    float offset_x, offset_y;
    const unsigned char *pixels;
} Sprite;
typedef struct { int node, screenblock; const unsigned short *map; } Background;

extern GbaNode nodes[];
extern const Shape shapes[];
extern const Sprite sprites[];
extern const Background backgrounds[];
extern const int node_count, shape_count, sprite_count, background_count, gba_bpp;
extern const unsigned short object_palette[], background_palette[];
extern const unsigned char background_tiles[], soundbank[];
extern const unsigned background_tiles_size;
extern const int has_audio;
void scripts_ready(void);
void scripts_tick(float delta);
void sounds_ready(void);
void move_body(int index);
void play_sound(int sample, int volume);
int gba_key_held(unsigned key);
int gba_key_hit(unsigned key);
float gba_divf(float a, float b);
int gba_divi(int a, int b);
int gba_modi(int a, int b);
static inline Vec2 gba_vec_add(Vec2 a, Vec2 b) { return (Vec2){a.x+b.x,a.y+b.y}; }
static inline Vec2 gba_vec_sub(Vec2 a, Vec2 b) { return (Vec2){a.x-b.x,a.y-b.y}; }
static inline Vec2 gba_vec_scale(Vec2 a, float b) { return (Vec2){a.x*b,a.y*b}; }
static inline float clamp_value(float a, float low, float high) { return a<low?low:a>high?high:a; }
static inline float approach(float a, float b, float step) { return a<b?fminf(a+step,b):fmaxf(a-step,b); }
#endif
