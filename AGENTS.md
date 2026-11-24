# Wytyczne architektoniczne dla Codexa (PolyFitter)

- **Jednostki:** Wyłącznie milimetry (`mm`) we wszystkich strukturach danych, obliczeniach i eksportach.
- **Układ współrzędnych:** Oś pionowa (góra–dół) to **oś Y** (`Y-up`), zgodna z bryłą odniesienia (`avatar.obj`).
- **Cel dopasowania (v1 — hełm):** Prześwit wewnętrzny **2–4 mm** w strefach przylegania do głowy, bez przenikania trójkątów.
- **Architektura:** Cała logika geometryczna i obliczeniowa znajduje się w `core/` jako czysty kod Pythona (z `type hints` i `dataclasses`), całkowicie oddzielony od warstwy UI. Każdy moduł w `core/` wymaga testów jednostkowych w `tests/`.
- **Błędy Armorsmitha, których nie wolno powielać:** Nie stosujemy uproszczonego sprawdzania kolizji na pojedynczej komórce siatki XY (FitChecker) ani zerowania pozycji obiektu w scenie przy eksporcie STL.
