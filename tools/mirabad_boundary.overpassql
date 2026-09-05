/* SafeRoad AI — граница Мирабадского района и светофоры.
   Запустить на https://overpass-turbo.eu → Run → Export → raw OSM data (JSON).

   Первый запрос дал геометрию улиц, но без двух вещей:
   границы района (иначе карта охватывает пол-Ташкента) и светофоров
   (сейчас режим перекрёстка угадывается по классу дороги, а не берётся из данных). */

[out:json][timeout:90];
(
  relation["boundary"="administrative"]["name"~"Mirobod|Мирабад|Mirabad",i];
  node["highway"="traffic_signals"](41.270,69.240,41.320,69.330);
);
out geom;
