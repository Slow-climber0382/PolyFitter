# Dane modelu człowieka

`app/human-data.mjs` zawiera dane z siatki bazowej hm08 MakeHuman oraz odpowiadającego jej szkieletu, wag i wybranych morfów. Pochodzą z [MakeHuman, rewizja a8bc2d54](https://github.com/makehumancommunity/makehuman/tree/a8bc2d54ff0ac92e78ff71431b1023eda42bf482/makehuman/data). Dane graficzne są objęte [CC0 1.0](LICENSE.MAKEHUMAN.md). Autorzy i szczegóły rozdzielenia licencji kodu i aktywów są opisane w [licencji MakeHuman](https://github.com/makehumancommunity/makehuman/blob/a8bc2d54ff0ac92e78ff71431b1023eda42bf482/LICENSE.md). Kod PolyFitter zachowuje odrębną licencję Apache-2.0.

## Odtworzenie danych

Pobierz następujące pliki z katalogu `makehuman/data` z przypiętej rewizji. Umieść je w jednym katalogu wejściowym pod ich oryginalnymi nazwami.

- `3dobjs/base.obj`
- `rigs/default.mhskel` oraz `rigs/default_weights.mhw`
- `targets/macrodetails/caucasian-female-young.target` oraz `targets/macrodetails/caucasian-male-young.target`
- `targets/nose/nose-scale-depth-incr.target`, `nose-scale-horiz-incr.target`, `nose-scale-vert-incr.target` i `nose-trans-up.target` z tego samego katalogu

```sh
python3 tools/import-makehuman.py katalog-wejściowy app/human-data.mjs
```

Importer wyciąga widoczną siatkę ciała i oczu, pomija pomocniczą geometrię rigowania, dzieli quady na trójkąty i skupia wagi na stawach wykorzystywanych przez cztery pozy PolyFitter. Presety pozy, przeliczanie pomiarów i kod podglądu są częścią PolyFitter. Gotowa aplikacja korzysta z dołączonych danych lokalnie.

## Earcut

Podział STL korzysta z kodu triangulacji Earcut 3.0.2 (Mapbox), licencja ISC. Kod pobrany z przypiętego tagu https://github.com/mapbox/earcut/tree/v3.0.2, plik `src/earcut.js`. Zachowana licencja znajduje się w `app/vendor/LICENSE.earcut`. Earcut trianguluje przekroje, a PolyFitter sprawdza szczelność wyniku przed eksportem.
