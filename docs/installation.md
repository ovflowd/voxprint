# Installation

Voxprint has two parts: the **app**, which turns an utterance into a voice embedding, and the
**integration**, which listens to your satellites and keeps the voiceprints. The app is separate
because onnxruntime, which runs the model, has no build for the Alpine Linux that Home Assistant's own
container uses.

## Home Assistant OS

1. **Add the repository to the app store.** Settings → Apps → App store → ⋮ → Repositories, and add
   `https://github.com/ovflowd/voxprint`.
2. **Install the app.** Find **Voxprint** in the store, install it, turn on *Watchdog* and start it.
   Its log should end with `Voxprint app 0.1.0, model wespeaker_resnet34_lm, self-test norm 1.0`.
   The image is about 450 MB, prebuilt for amd64 and aarch64.
3. **Install the integration.** In the Marketplace (HACS), ⋮ → Custom repositories, add the same URL
   with the type *Integration*, open **Voxprint** and download it. Restart Home Assistant: a new
   integration is only found at start.
4. **Add the integration.** Settings → Devices & services → Add integration → **Voxprint**. The app's
   URL is filled in from the installed app, as `http://<hostname>:10340`; the hostname is on the app's
   info page if you need it. Choose the satellites to listen to. Voxprint checks that the app answers
   and runs the model it expects.

Then add speakers and enroll them: [enrollment.md](enrollment.md).

## Home Assistant Container, or Core

There is no app store, so run the app's image yourself, next to Home Assistant:

```bash
docker run -d --name voxprint --restart unless-stopped -p 127.0.0.1:10340:10340 ghcr.io/ovflowd/voxprint:0.1.0
```

Use `http://localhost:10340` as the app URL when Home Assistant runs on the same host with host
networking, or the container's name on a shared Docker network. Keep the port off your LAN: the app
has no authentication, and anyone who can reach it can make it compute embeddings. It never stores
anything.

Install the integration from the Marketplace as above, or copy `custom_components/voxprint` from a
release into your configuration's `custom_components` folder and restart.

## Updating

- The integration updates from the Marketplace. Each update needs a restart.
- The app updates from the app store. Its version is independent of the integration's; the
  integration checks at setup that the app speaks its API version and runs its model.

## Removing

1. Settings → Devices & services → Voxprint → ⋮ → Delete. The tee comes off every STT entity at once,
   without a restart, and every voiceprint is deleted.
2. Uninstall the app, and remove the integration in the Marketplace.
3. Scripts that read a speaker sensor see it disappear. Make sure a missing sensor means "unknown"
   to them, as in [automations.md](automations.md).
