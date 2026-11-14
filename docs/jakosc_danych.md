| Problem | Zakres | Planowane działanie | Kto |
| :--- | :--- | :--- | :--- |
| Brakujące wartości w kolumnie average_playtime_forever_min oraz median_playtime_forever_min | całe kolumny | usunięcie zmiennych ze skryptu pobierającego dane oraz wykluczenie ich z dalszych rozważań | Norbert Kabziński |
| Brakujące wartości w kolumnie metacritic_score | ~83% rekordów | wykluczenie zmiennej z jej udziału w dalszej analizie | Paweł Lechowicz |
| | | | |
| Wysoka współliniowość: Informacje o cenie price_initial_usd i price_final_usd oraz popularności positive_reviews, negative_reviews, ccu | cały zbiór danych | Po analizie stwierdzono, że zmienne dostarczają osobno istotnie informacje pomimo wysokiej współliniowości z tego powodu zostaną w zbiorze. | Szymon Ciućka |
| W kolumnach publishers oraz developers puste wartości znakowe. | Cały zbiór | Pozostawienie zmiennych w zbiorze. Analiza wykazała, że brak wydawcy i developera do paru nie popularnych gier nie będzie miał większego wpływu na dalszą analizę | Szymon Ciućka |
