/* ecobasa-map.js — shared OpenLayers utilities
 * Requires: OL v7 must be loaded before any EcoMap function is called.
 * Loaded in base.html so it is available on all pages.
 * Stadia API key is read from data-stadia-key on the <script> tag itself.
 */
(function () {
  'use strict';

  var _stadiaKey = (document.currentScript || document.querySelector('script[data-stadia-key]') || {}).dataset.stadiaKey || '';

  function stadiaUrl(tile, ext) {
    var suffix = _stadiaKey ? '?api_key=' + _stadiaKey : '';
    return 'https://tiles.stadiamaps.com/tiles/' + tile + '/{z}/{x}/{y}.' + (ext || 'png') + suffix;
  }

  window.EcoMap = {

    // ── Icon rendering ───────────────────────────────────────────────

    // badge: integer codepoint like 0xF007 ( fa-user),
    //        or a JS unicode escape string like ''
    createLayeredIcon(badge, pinColor, badgeColor) {
      badgeColor = badgeColor || '#fcf3e5';
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      const size = 80;
      canvas.width = canvas.height = size;
      ctx.fillStyle = pinColor;
      ctx.font = '900 60px "' + 'Font Awesome 6 Free' + '"';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(String.fromCodePoint(0xF041), size / 2, size / 2); //  fa-map-marker pin body
      ctx.fillStyle = badgeColor;
      ctx.font = '900 25px "' + 'Font Awesome 6 Free' + '"';
      ctx.fillText(typeof badge === 'number' ? String.fromCodePoint(badge) : badge, size / 2, size / 2.5);
      return canvas;
    },

    makeIconStyle(badge, pinColor, badgeColor) {
      return new ol.style.Style({
        image: new ol.style.Icon({
          img: this.createLayeredIcon(badge, pinColor, badgeColor),
          imgSize: [80, 80], anchor: [0.5, 0.85], scale: 0.7
        })
      });
    },

    // ── Base tile layers ─────────────────────────────────────────────

    buildBaseLayers() {
      const wc = new ol.layer.Tile({
        visible: false,
        source: new ol.source.XYZ({ url: stadiaUrl('stamen_watercolor', 'jpg'), crossOrigin: 'anonymous' })
      });
      const toner = new ol.layer.Tile({
        visible: false, opacity: 0.35,
        source: new ol.source.XYZ({ url: stadiaUrl('stamen_toner_lite'), crossOrigin: 'anonymous' })
      });
      const sat = new ol.layer.Tile({
        visible: false,
        source: new ol.source.XYZ({
          url: 'https://mt{0-3}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}',
          attributions: '&copy; Google', maxZoom: 20, crossOrigin: 'anonymous'
        })
      });
      const osm = new ol.layer.Tile({
        visible: false,
        source: new ol.source.OSM({ url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', crossOrigin: 'anonymous' })
      });
      const groups = { ecobasa: [wc, toner], satellite: [sat], osm: [osm] };
      const all = [wc, toner, sat, osm];
      const setBaseLayer = (key) => {
        Object.entries(groups).forEach(function (entry) {
          entry[1].forEach(function (l) {
            const on = entry[0] === key;
            l.setVisible(on);
            l.setZIndex(on ? 0 : -1);
          });
        });
      };
      return { wc, toner, sat, osm, all, groups, setBaseLayer };
    },

    // ── Layer toggle control ─────────────────────────────────────────

    // Returns the menu element so caller can bind setBaseLayer to radio changes.
    buildLayerToggle(map, groupName, trans) {
      trans = Object.assign({ title: 'Map style', ecobasa: 'ecobasa', satellite: 'Satellite', osm: 'OSM' }, trans || {});
      const wrap = document.createElement('div');
      wrap.className = 'absolute top-2.5 right-2.5';
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'flex items-center justify-center w-12 h-12 rounded-md bg-primary bg-opacity-80 text-secondary shadow-lg border border-red backdrop-blur';
      btn.innerHTML = '<i class="fa fa-layer-group text-lg"></i>';
      const menu = document.createElement('div');
      menu.className = 'hidden absolute right-0 w-44 bg-primary text-secondary bg-opacity-80 backdrop-blur rounded-lg shadow-xl border border-red py-2';
      menu.innerHTML =
        '<div class="px-3 pb-1 text-xs font-semibold uppercase">' + trans.title + '</div>' +
        '<ul class="list-none m-0 text-sm space-y-1 px-2">' +
          '<li><label class="dropdown-item hover:bg-opacity-10 hover:text-secondary"><input type="radio" name="' + groupName + '" value="ecobasa" class="form-radio light mr-2" checked><span>' + trans.ecobasa + '</span></label></li>' +
          '<li><label class="dropdown-item hover:bg-opacity-10 hover:text-secondary"><input type="radio" name="' + groupName + '" value="satellite" class="form-radio light mr-2"><span>' + trans.satellite + '</span></label></li>' +
          '<li><label class="dropdown-item hover:bg-opacity-10 hover:text-secondary"><input type="radio" name="' + groupName + '" value="osm" class="form-radio light mr-2"><span>' + trans.osm + '</span></label></li>' +
        '</ul>';
      wrap.appendChild(btn);
      wrap.appendChild(menu);
      map.getViewport().appendChild(wrap);
      const show = function () { menu.classList.remove('hidden'); btn.classList.add('hidden'); };
      const hide = function () { menu.classList.add('hidden'); btn.classList.remove('hidden'); };
      btn.addEventListener('mouseenter', show);
      btn.addEventListener('click', function (e) { e.stopPropagation(); show(); });
      menu.addEventListener('mouseleave', hide);
      document.addEventListener('click', function (e) { if (!wrap.contains(e.target)) hide(); });
      return menu;
    },

    // ── Geocoding ────────────────────────────────────────────────────

    async reverseGeocode(lon, lat) {
      try {
        const r = await fetch('https://nominatim.openstreetmap.org/reverse?format=json&lat=' + lat + '&lon=' + lon + '&addressdetails=1');
        return await r.json();
      } catch (e) { return null; }
    },

    applyGeoToForm(geo, inputs) {
      inputs = inputs || {};
      if (!geo || !geo.address) return;
      if (geo.address.country_code && inputs.countryInput)
        inputs.countryInput.value = geo.address.country_code.toUpperCase();
      const a = geo.address;
      const city = a.city || a.town || a.village || a.hamlet || a.municipality || '';
      const parts = [
        [a.road, a.house_number].filter(Boolean).join(' '),
        [a.postcode || '', city].filter(Boolean).join(' '),
        a.state || a.region || a.county || '',
        a.country || ''
      ].filter(Boolean);
      if (parts.length && inputs.nameInput) inputs.nameInput.value = parts.join(', ');
    },

    // ── Location picker widget ───────────────────────────────────────

    initLocationPicker(cfg) {
      const badge     = cfg.badge !== undefined ? cfg.badge : 0xF007; //  fa-user
      const pinColor  = cfg.pinColor || '#da6137';
      const groupName = cfg.groupName || 'loc-layer';
      const zoom      = cfg.zoom || 12;
      const self      = this;

      const vectorSource = new ol.source.Vector();
      const feature = new ol.Feature();
      vectorSource.addFeature(feature);

      const vectorLayer = new ol.layer.Vector({
        source: vectorSource,
        style: this.makeIconStyle(badge, pinColor)
      });

      const layers = this.buildBaseLayers();
      const map = new ol.Map({
        target: cfg.mapTarget,
        layers: layers.all.concat([vectorLayer]),
        view: new ol.View({ center: ol.proj.fromLonLat([0, 20]), zoom: 2, maxZoom: 18 })
      });
      layers.setBaseLayer('ecobasa');

      const menu = this.buildLayerToggle(map, groupName, cfg.layerTrans);
      menu.querySelectorAll('input').forEach(function (r) {
        r.addEventListener('change', function (e) { if (e.target.checked) layers.setBaseLayer(e.target.value); });
      });

      const setPoint = function (lon, lat, opts) {
        opts = opts || {};
        const coords = ol.proj.fromLonLat([parseFloat(lon), parseFloat(lat)]);
        feature.setGeometry(new ol.geom.Point(coords));
        if (!opts.skipZoom) map.getView().animate({ center: coords, zoom: zoom });
        if (cfg.locationInput) cfg.locationInput.value = 'POINT (' + lon + ' ' + lat + ')';
        if (opts.label && cfg.nameInput) cfg.nameInput.value = opts.label;
        if (opts.country && cfg.countryInput) cfg.countryInput.value = opts.country;
      };

      if (cfg.setPointFn) {
        window[cfg.setPointFn] = function (lon, lat, label, country) {
          setPoint(lon, lat, { label: label, country: country || '' });
        };
        window[cfg.setPointFn + '_clear'] = function () {
          feature.setGeometry(null);
          if (cfg.locationInput) cfg.locationInput.value = '';
        };
      }

      map.on('click', async function (evt) {
        const lonlat = ol.proj.toLonLat(evt.coordinate);
        setPoint(lonlat[0], lonlat[1], { skipZoom: true });
        self.applyGeoToForm(await self.reverseGeocode(lonlat[0], lonlat[1]), cfg);
      });

      const modify = new ol.interaction.Modify({ source: vectorSource });
      modify.on('modifyend', async function () {
        const geom = feature.getGeometry();
        if (!geom) return;
        const lonlat = ol.proj.toLonLat(geom.getCoordinates());
        setPoint(lonlat[0], lonlat[1], { skipZoom: true });
        self.applyGeoToForm(await self.reverseGeocode(lonlat[0], lonlat[1]), cfg);
      });
      map.addInteraction(modify);

      if (cfg.existingWkt) {
        const m = cfg.existingWkt.match(/POINT\s*\(\s*([\d.\-]+)\s+([\d.\-]+)\s*\)/i);
        if (m) setPoint(parseFloat(m[1]), parseFloat(m[2]));
      }

      if (cfg.locateFn) {
        window[cfg.locateFn] = function () {
          if (!navigator.geolocation) return;
          navigator.geolocation.getCurrentPosition(async function (pos) {
            setPoint(pos.coords.longitude, pos.coords.latitude);
            self.applyGeoToForm(await self.reverseGeocode(pos.coords.longitude, pos.coords.latitude), cfg);
          });
        };
      }

      return { map, setPoint, vectorLayer, feature, layers };
    },

    // ── Alpine.js location search dropdown ──────────────────────────

    // Usage in template: x-data="EcoMap.locationDropdown('setUserPoint')"
    locationDropdown(setPointFn) {
      return {
        results: [], open: false, loading: false,
        async onInput(query) {
          const term = (query || '').trim();
          if (!term) {
            this.results = []; this.open = false;
            if (window[setPointFn + '_clear']) window[setPointFn + '_clear']();
            return;
          }
          this.loading = true;
          try {
            const r = await fetch('https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&q=' + encodeURIComponent(term));
            const data = await r.json();
            this.results = data.slice(0, 5);
            this.open = this.results.length > 0;
          } catch (e) { this.results = []; this.open = false; }
          finally { this.loading = false; }
        },
        onSelect(res) {
          const lon = parseFloat(res.lon), lat = parseFloat(res.lat);
          const country = (res.address && res.address.country_code) ? res.address.country_code.toUpperCase() : '';
          if (Number.isFinite(lon) && Number.isFinite(lat) && window[setPointFn]) {
            window[setPointFn](lon, lat, res.display_name || '', country);
          }
          this.results = []; this.open = false;
        }
      };
    }
  };
})();
