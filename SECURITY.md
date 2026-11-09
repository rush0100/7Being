# Security notes

Local-first BCI stack. Treat the GUI HTTP server as **loopback-only**.

## Hardening in place

- GUI binds `127.0.0.1` by default.
- Profile ids are jailsafed (`safe_profile_id` / `profile_dir`) — no `../` path escape under `~/.7beingbci/profiles`.
- `mental.joblib` / `calibration.npz` load only from inside the profile store, fixed filenames.
- Keyboard injection (`/keys` + `post_key`) requires loopback client, `keys_enabled`, and a single-character whitelist from the keymap.

## Still local-trust

- No auth on the GUI HTTP API — anyone on the same machine can call it while it runs.
- `joblib`/`pickle` models are trusted only because they live in the jailsafed profile dir; do not copy unknown `.joblib` files into profiles.
- Device gRPC daemons are expected on localhost; do not expose them to the LAN without TLS + auth.

## Publish guidance

`7Being`, `7being-ads1299`, and `7being-studio` are the public MIT set.  
Keep **`7being-h1`** private — it speaks the vendor frame format.  
Keep **`7being-emotiv-epocx`** private.
