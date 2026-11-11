# PolyFitter — Przeczytaj mnie

[English README](README.md)

Otwartoźródłowa aplikacja przeglądarkowa do dopasowywania modeli 3D zbroi i rekwizytów
do wymiarów użytkownika. Wczesna wersja 0.6.2; poprzednia nazwa robocza: ForgeFit.

## Uruchomienie

Docelowy adres: https://slow-climber0382.github.io/PolyFitter/ — zacznie działać po
włączeniu GitHub Pages i udanej publikacji. Program przetwarza modele i pomiary
lokalnie w przeglądarce. Nie wymaga konta ani przesyłania STL na serwer.
Zapisuj projekty: zamknięcie lub odświeżenie karty usuwa niezapisane zmiany.
Interfejs jest obecnie po polsku; pozostałe języki są planowane.

## Co działa

- Import binarnych i tekstowych STL, wybór mm/cm/cali, kontrola siatki.
- Regulowany manekin neutralny, męski i żeński, pomiary szczegółowe oraz pozy.
- Wstępny automat dla hełmu, napierśnika i dwóch typów ochraniacza goleni.
- Ręczna skala proporcjonalna lub niezależne XYZ, obrót, przesunięcie i orientacja.
- Przybliżona kontrola kolizji, mapa dopasowania i próba wsunięcia hełmu; pianka na czubku.
- Wiele części w projekcie i wspólne transformacje zestawów hełmu.
- Cofnij/Ponów do 40 zmian, również pomiarów oraz importu/usunięcia części.
- Zapis i odczyt `.polyfitter`, odczyt wcześniejszych `.meshavon` i `.forgefit`, eksport STL w mm.
- Eksperymentalny podział płaszczyznami na zamknięte części do druku.

LPM obraca, PPM przesuwa, rolka przybliża. Dostępne są sześć rzutów i kadrowanie.
Ctrl/Cmd+Z oraz Ctrl/Cmd+Shift+Z działają poza polami tekstowymi; w polach pozostaje
standardowe cofanie wpisywanego tekstu. Przeglądarka może pytać o wiele pobrań
przy eksporcie zestawu. Sprawdź, czy wszystkie pliki zostały pobrane.

## Ograniczenia

Automat nie rozpoznaje anatomii ani wizjera STL. Najpierw ustaw orientację; później
obejrzyj oczy, brodę, nos i skorupę z kilku stron. Brak końcowej kolizji nie oznacza,
że hełm da się założyć. Testowane rzeczywiste hełmy nadal nie przechodzą próby wsunięcia,
a część goleni daje odrzucane, zbyt duże wyniki. Nie potwierdzono gotowości do druku,
wygody ani pola widzenia. Manekin jest przybliżony; nie każdy wymiar jest odtwarzany
niezależnie i dokładnie. Scena pokazuje aktywną część lub zestaw hełmu, nie wszystkie
osobne elementy jednocześnie. Przykładowy hełm jest proceduralny.

Limit STL: 1 mln trójkątów. Projekt: 2 mln trójkątów i 150 MB. Duże siatki mogą powodować
pauzy przy obliczaniu raportu kolizji. Potrzebne WebGL i workery modułowe w przeglądarce.
Firefox, Safari i urządzenia mobilne wymagają dalszej weryfikacji.

## Rozwój lokalny

Node.js co najmniej 22.12; brak zależności npm:

```sh
npm test
npm run build
npm start
```

Otwórz http://127.0.0.1:8080, nie plik przez `file://`.
Do hostowania wystarcza katalog `dist/`. Electron nie jest wymagany.

## Plan

Najpierw lepsze ustawianie hełmu i dopasowanie ciała, profile pomiarów, OBJ/3MF i języki.
Później szablony papierowe, maski do malowania oraz dalsze narzędzia druku i odlewów.
To plany, a nie funkcje dostępne obecnie.

## Współpraca

Wykonaj fork i zgłoś pull request z opisem konkretnych zmian i testów.
Wymagamy przeglądu opiekuna projektu przed przyjęciem zmian. Autor nie zatwierdza
własnego PR. [CONTRIBUTING.md](CONTRIBUTING.md) opisuje zasady; [MAINTAINERS.md](MAINTAINERS.md)
ustawienia GitHuba potrzebne do ich egzekwowania. Sam plik CODEOWNERS nie blokuje scalania.

## Licencja i własne wersje

Kod: [Apache 2.0](LICENSE). Możesz rozwijać i wydawać własną wersję, także komercyjną.
Zachowaj wymagane informacje o prawach, licencji i pochodzeniu, odpowiednią treść
[NOTICE](NOTICE) oraz wyraźnie oznacz zmienione pliki zgodnie z punktem 4 licencji.
Prosimy również o konkretny opis zmian w README lub CHANGELOG własnej wersji.
Sama Apache 2.0 wymaga oznaczenia zmienionych plików, ale nie szczegółowego publicznego
dziennika zmian. Nie wymaga publikowania kodu forka ani naszej zgody na jego wydanie.

Projekt źródłowy: https://github.com/Slow-climber0382/PolyFitter

Dane manekina MakeHuman pozostają na CC0, Earcut na ISC; szczegóły w [ASSETS.md](ASSETS.md).
Wcześniejsze kopie ForgeFit udostępnione na MIT zachowują tę licencję.
