# Vendored frontend assets

The app is served fully offline. No page loads anything from a CDN, so the demo
works without network access and makes no third-party requests.

| Package | Version | Source | License |
|---|---|---|---|
| Chart.js | 4.5.1 | `npm pack chart.js@4.5.1` → `dist/chart.umd.min.js` | MIT (`chartjs-4.5.1/LICENSE.md`) |
| Font Awesome Free | 6.7.2 | `npm pack @fortawesome/fontawesome-free@6.7.2` → `css/all.min.css`, `webfonts/*.woff2` | Icons CC BY 4.0, fonts SIL OFL 1.1, code MIT (`fontawesome-free-6.7.2/LICENSE.txt`) |

Local changes:

- `chart.umd.min.js`: the trailing `//# sourceMappingURL=` comment was removed
  (the map is not vendored). Otherwise byte-identical.
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
```

Verify with `cd public/vendor && sha256sum -c` on the block above.

To upgrade: `npm pack <pkg>@<version>`, copy the same files into a new
versioned folder, update the `<link>`/`<script>` tags in `public/index.html`
and `public/main.html`, and refresh this table.
