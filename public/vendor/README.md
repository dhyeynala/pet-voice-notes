# Vendored frontend assets

The app is served fully offline. No page loads anything from a CDN, so the demo
works without network access and makes no third-party requests.

| Package | Version | Source | License |
|---|---|---|---|
| Chart.js | 4.5.1 | `npm pack chart.js@4.5.1` → `dist/chart.umd.min.js` | MIT (`chartjs-4.5.1/LICENSE.md`) |
| Font Awesome Free | 6.7.2 | `npm pack @fortawesome/fontawesome-free@6.7.2` → `css/all.min.css`, `webfonts/*.woff2` | Icons CC BY 4.0, fonts SIL OFL 1.1, code MIT (`fontawesome-free-6.7.2/LICENSE.txt`) |
| Firebase JS SDK (app + auth) | 12.19.0 | `npm pack firebase@12.19.0` (tarball sha256 `e48742de0b655887eca893b1292932563b80aaf1ebf184b6fdb2b4c5290da3ce`) → `firebase-app.js`, `firebase-auth.js` (the browser ESM builds also served from gstatic) | Apache-2.0 (`firebase-12.19.0/LICENSE`, from the firebase-js-sdk repo at tag `firebase@12.19.0`) |

Local changes:

- `chart.umd.min.js`: the trailing `//# sourceMappingURL=` comment was removed
  (the map is not vendored). Otherwise byte-identical.
- Firebase: `firebase-auth.js` imports `./firebase-app.js` instead of
  `https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js`, and the trailing
  `//# sourceMappingURL=` comments were removed from both files. Otherwise byte-identical
  (upstream sha256: `firebase-app.js` `39a50952b5def557337b2290069c7d7371f3515ad46c44a43b9c520f734d8d14`,
  `firebase-auth.js` `59f60ce3adcb4c85a5260e963fd14134eec088de5b18ddfb9e95771c72f65264`).
  The SDK is loaded only when the server enables Firebase sign-in (`js/firebase.js`, via
  `import()`); demo mode never fetches it. In Firebase mode the browser does talk to Google
  (Identity Toolkit, the `<project>.firebaseapp.com` sign-in pop-up, and `apis.google.com` for the
  pop-up helper): that is inherent to Firebase sign-in, and opt-in.
- Font Awesome: only the `.woff2` webfonts are vendored. `all.min.css` also
  lists `.ttf` fallbacks, which are only requested by browsers without woff2
  support (none of the supported browsers).

## sha256

```
31afbecadaef6da89edf023df400e08b3dfb44dd099c57e711d5e69c4c731784  chartjs-4.5.1/chart.umd.min.js
74005d7c17d4a02f2f25404ec0655d9bc2fdaa53166874c87d7b7eec69d9088a  fontawesome-free-6.7.2/css/all.min.css
d7236a19bf23cbb2027280e8f51dc99d6c45976a2ed60de73382b034b18a2b68  fontawesome-free-6.7.2/webfonts/fa-brands-400.woff2
e3456d1283b9d75337a773dfd147bf908fd02c01b4bf48576d8603a69b13cbe5  fontawesome-free-6.7.2/webfonts/fa-regular-400.woff2
aa75998623a391e61c6901794ace832e3ecdd288b56d608f21bea0411acc0b8e  fontawesome-free-6.7.2/webfonts/fa-solid-900.woff2
0ce9033c69dc714f5f45ef9bf17d55e4c46bcdfad6799a4e92b38e7781bf86bd  fontawesome-free-6.7.2/webfonts/fa-v4compatibility.woff2
b4e6359ec15648bff062dd1b6697b764ee66ba99f14e4f6d704390353dc5e870  firebase-12.19.0/firebase-app.js
ed36687bda5ba3337dc7af5451f72cf53cac044139cc255ad8c31cc1e52492b2  firebase-12.19.0/firebase-auth.js
```

Verify with `cd public/vendor && sha256sum -c` on the block above.

To upgrade: `npm pack <pkg>@<version>`, copy the same files into a new
versioned folder, update the `<link>`/`<script>` tags in `public/index.html`
and `public/main.html` (Firebase: the imports in `public/js/firebase.js` and the
rewritten import in `firebase-auth.js`), and refresh this table.
