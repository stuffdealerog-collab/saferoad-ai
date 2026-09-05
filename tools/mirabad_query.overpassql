/* SafeRoad AI — дорожная сеть Мирабадского района, Ташкент.
   Запустить на https://overpass-turbo.eu  → Run → Export → raw OSM data (JSON).

   Границы заданы прямоугольником; при необходимости подвиньте цифры
   (порядок: юг, запад, север, восток). Текущий охват — центрально-южная
   часть Ташкента, куда попадает Мирабадский район. */

[out:json][timeout:120];
(
  way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|residential|unclassified|living_street)$"]
     (41.270,69.240,41.320,69.330);
);
out body geom;
