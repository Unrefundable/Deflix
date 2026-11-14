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
