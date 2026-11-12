# Pomiary i ograniczenia — PolyFitter 0.1

Porównanie wykonano 10 listopada 2026 z dokumentacją autorów ArmorSmith:

- [Body measurements](https://github.com/TheArmoredGarage/Armorsmith-Documents/blob/main/avatar/body-measurements.mdx)
- [Creating your avatar](https://github.com/TheArmoredGarage/Armorsmith-Documents/blob/main/avatar/creating-your-avatar.mdx)
- [Chest and breast shape](https://github.com/TheArmoredGarage/Armorsmith-Documents/blob/main/avatar/chest-and-breast-shape.mdx)

Dokumentacja opisuje wzrost, długości tułowia i segmentów kończyn, sumy długości ręki i nogi, obwody oraz regulację proporcji przekrojów. Regulacja szczegółów twarzy i biustu jest regulacją kształtu, nie bezpośrednim odczytem miary krawieckiej. Nie znaleziono w powyższych stronach osobnych pomiarów palców ani specyfikacji blokad każdego wymiaru. Nie traktujemy tych funkcji jako potwierdzonej zgodności.

| Obszar | Stan w serii 0.1 |
| --- | --- |
| Głowa | Kalibracja obwodu na poziomym przekroju czoła, niezależna wysokość |
| Szyja, barki | Kalibracja barków i obwodów szyi; długość szyi z pionowych punktów odniesienia |
| Tułów | Dodane proporcje przekrojów oraz niezależna wielkość/wysokość biustu i wielkość pośladków |
| Ręce | Blokada ramienia/przedramienia przy zmianie sumy, proporcje przekrojów |
| Nogi | Blokada uda/goleni przy zmianie sumy, proporcje przekrojów |
| Miary złożone | Zachowują zablokowany segment; dwie blokady odrzucają zmianę |
| Palce | Brak; kształt dłoni pochodzi z siatki MakeHuman |
| Prowadnice pomiarowe | Brak kompletu prowadnic dla każdego pola; linie podziału nie są pełnym systemem prowadnic |
| Wszystkie wymiary 1:1 | Niepotwierdzone, szczególnie wszystkie obwody rąk, długości dłoni/stóp i szczegóły twarzy |

## Definicje i dokładność

- Wysokość głowy jest liczona od poziomu podbródka do czubka. Obwód jest obwodem wypukłego przekroju siatki na poziomie czoła nad brwiami, bez nosa i uszu.
- Szyja jest pionowym odcinkiem między punktami odniesienia pod brodą i przy podstawie szyi. Nie jest długością po krzywiźnie skóry.
- Barki mierzymy w pozycji pomiarowej jako szerokość przekroju górnej części mięśni naramiennych. To nie jest odległość między środkami stawów. Pozy zmieniają projekcję szerokości.
- Symetria to maksymalna różnica między sparowanymi wierzchołkami po odbiciu względem X=0; parowanie siatki źródłowej wykorzystuje tolerancję 0,001 jednostki źródłowej. Nie stanowi pełnego pomiaru odległości Hausdorffa.
- Odchylenie osi tułowia mierzymy jako przesunięcie środka przekroju w bok na czterech poziomach. Nie mierzymy fizycznego kręgosłupa ani nie usuwamy naturalnej krzywizny sylwetki widocznej z boku.
- Dla głowy 545/250 mm, wszystkich trzech typów i wzrostu 1750 mm oba cele głowy mieszczą się w tolerancji 0,01 mm w geometrii Float32. Taka dokładność obliczeniowa nie oznacza takiej dokładności pomiaru człowieka lub druku.
- Dodatkowy test obwodów tułowia obejmuje szyję 390, podstawę szyi 420, klatkę 1020, pod biustem 960, talię 850, górne biodra 920, biodra 980 mm; błąd geometryczny każdego badanego przekroju jest poniżej 0,1 mm. Nie zbadano całego zakresu kombinacji parametrów.
- Pozostałe regulatory deformują bazową siatkę, lecz nie mają jeszcze niezależnej kalibracji i walidacji każdej możliwej wartości. Manekin nie jest gotowy do obietnicy pełnego odwzorowania osoby 1:1.

## Hełm i druk

Test Commander Fox nie został wykonany: nie dostarczono jego plików STL. Test na skorupie demonstracyjnej wykorzystuje obwód 545 mm, wysokość 250 mm, **testową** piankę 3 mm i luz 0. Właściwą grubość pianki trzeba wpisać zgodnie z użytym materiałem.

Otoczka dopasowania jest konserwatywna. Ustawienie luzu 0 oznacza brak dodanego zapasu w konfiguracji; nie gwarantuje styku całej powierzchni hełmu z głową ani dokładnego braku pustej przestrzeni. Nie wykrywa semantycznie pozycji oczu, „zębów” wizjera czy dolnej krawędzi brody. Do tego służy podgląd i ręczne ustawienie. Nos i uszy biorą udział w kontroli geometrii.

Podział do druku działa dla poprawnych zamkniętych siatek. Eksport jest blokowany, jeśli wynik nie przechodzi kontroli szczelności. Nie ma jeszcze automatycznych kołków montażowych, wyboru szwów względem detali hełmu ani optymalizacji podpór. Limit obrysu części wynika z podanych wymiarów drukarki X/Y/Z pomniejszonych o zapas. Domyślnie jest to 245 mm na każdej osi. Nie gwarantuje miejsca na podpory i brim w dowolnej orientacji.

Licencje siatki i szkieletu MakeHuman CC0 oraz triangulacji Earcut ISC są zachowane w repozytorium. Nie wykorzystano modeli z Unreal Engine ani ArmorSmith.
