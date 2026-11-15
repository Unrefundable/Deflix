# Deflix

Kodi skin with a streaming-focused layout.

## Install from GitHub Pages

Use this file source in Kodi:

```text
https://unrefundable.github.io/Deflix/
```

Then install `repository.deflix-1.0.3.zip` from the source and install the
skin from **Deflix Repository**.

Install the skin from the repository, not from a skin zip. The repository also
lists the add-ons Deflix depends on, so Kodi installs them along with the skin:
the Bingie add-ons (the Bingie repository and skin are not needed) and
[KDMM](https://github.com/Unrefundable/kdmm), which plays the movies and
episodes. Kodi only resolves those dependencies for add-ons installed from a
repository.

After installing, two sign-ins make everything work: Trakt in TMDb Bingie
Helper (Home is built from your Trakt rows) and Real-Debrid or AllDebrid in
KDMM's settings. KDMM sets itself as the helper's default player.

The GitHub Pages repository files are generated with:

```sh
python3 tools/build_kodi_repo.py
```

The build copies the current KDMM release from KDMM's own repository, so
publish KDMM first when the skin needs a newer version of it.

Between skin releases, the `Sync KDMM into the Deflix repository` workflow
checks hourly for a new KDMM release and publishes it into the repository on
`gh-pages` (`tools/sync_kdmm.py`), so devices receive KDMM updates without a
Deflix rebuild. It can also be started by hand from the Actions tab.

## Startup intro

The startup animation (`extras/media/deflix_intro_*.mp4`) and the still splash
image (`extras/media/deflix_splash.png`) are rendered from a script, so they
can be changed without video editing software:

```sh
pip install pillow        # once; ffmpeg must also be installed
python3 tools/build_intro.py
```

Everything about the look is in `tools/intro.json`. Edit it, then preview
before rendering the videos:

```sh
python3 tools/build_intro.py --sheet        # contact sheet of the whole animation
python3 tools/build_intro.py --frame 5.2    # a single frame
```

`"style"` picks the animation:

- `orbit` (current): the provider logos, drawn as rounded tiles like the
  sidebar icons, leave the centre one at a time and circle it, slowly at first
  and then ever faster until they smear into streaks of their own colours. The
  ring falls into the centre and bursts into those colours, which keep turning
  behind the Deflix wordmark before everything fades out.
- `showcase`: each streaming provider's logo appears with a short
  animation modelled on that provider's own intro, then all their colours turn
  slowly as one soft aura behind the Deflix wordmark.
- `classic`: the original Bingie animation with the Deflix wordmark.

### Orbit

The tiles are the lines of `orbit.logos`, in the order they appear. Each has a
`logo`, a `logo_scale` (how much of the tile it fills), a `background` (one
colour, or `[top, bottom]` for a gradient), an optional `logo_color` to
recolour the logo, and a `glow` colour used for its streak, the burst and the
final aura. Add a line to add a tile; the ring spaces them evenly.

| Setting | What it does |
|---|---|
| `stagger`, `emerge` | Seconds between tiles appearing, and how long each takes to reach the ring |
| `radius`, `tile` | Size of the ring and of the tiles, as fractions of the screen height |
| `spin` | Turning speed at the start and at the end, in radians per second |
| `accelerate` | When the speeding up starts and ends, in seconds |
| `streak_speed` | The speeds at which tiles begin to blur and at which they are fully streaks |
| `trail` | Length of the colour tails |
| `collapse`, `burst` | How long the ring takes to fall inwards, and the moment of the burst |
| `flash`, `burst_boost`, `sparks` | Length of the white flash, extra brightness of the burst, number of sparks |

`orbit.finale` has the same settings as the showcase finale below.

### Showcase providers

The providers are the lines of `showcase.providers`, shown in that order. Each
has a `logo` (a large transparent PNG in `tools/intro_logos/`), a
`logo_height` (fraction of the screen height), a `glow` colour (also its share
of the final aura) and an `effect`:

| Effect | Made for | What happens |
|---|---|---|
| `ribbon` | Netflix | The N is drawn stroke by stroke, then the camera dives in and it becomes strands of coloured light |
| `comet` | Disney+ | Light runs along the arc over a dark logo, flares at the plus, and the logo lights up on teal |
| `smile` | Prime Video | Blue rings sweep past, the name rises and the smile draws itself through to its arrow |
| `flare` | Apple TV+ | The logo comes out of black with a flare of light on the plus |
| `focus` | HBO Max | The logo starts huge, purple and out of focus, then pulls back sharp and white on a purple wash |
| `starring` | Paramount+ | Stars fly in and ring the mountain on blue, then the name appears (`wordmark` is the name's image) |
| `bloom` | anything else | The logo, or the `name` as text if there is no `logo`, over a soft glow |

The first six effects rely on the shape of that provider's logo, so use them
with those logos. To add another provider, save its logo in
`tools/intro_logos/` and add a line with `"effect": "bloom"`:

```json
{"name": "Hulu", "effect": "bloom", "logo": "tools/intro_logos/hulu.png", "logo_height": 0.15, "glow": "#1CE783"}
```

The video gets longer by itself. `provider_time` and `crossfade` set how long
each provider stays. `finale` holds the ending: `spin` is how fast the aura
turns, `softness` how blurred its colours are, `aura_strength` its brightness
and `pocket` how much it is darkened behind the wordmark.

The logos come from Wikimedia Commons (recoloured white where the intro needs
that; the Paramount emblem has the name removed from its dome). They are the
trademarks of their owners and are only used to build the video, so they stay
in `tools/` and are not packaged with the skin.

### Other settings

- `text`, `color`, `cap_height`, `bow`: the Deflix wordmark. The letters D, E,
  F, L, I and X are drawn by the script to match the original Bingie
  lettering; other characters use `fallback_font`, and setting `font` to a
  font file uses that font for every letter.
- `quality`: video compression, lower is better and larger (18 to 26 is the
  useful range).
- A new animation is a new style: add a function next to `style_showcase` in
  `tools/build_intro.py` and register it in `STYLES`. A new provider animation
  is a function registered in `EFFECTS`.
