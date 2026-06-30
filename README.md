# Analiza i optimizacija MongoDB baze o evropskim restoranima

Ovaj projekat se bavi analizom skupa podataka o restoranima sa TripAdvisor-a.
Podaci su modelovani u MongoDB bazi, nad njima su definisani analiticki upiti,
izmerene su performanse pre optimizacije, a zatim je napravljena optimizovana
sema sa indeksima i uporedeni su rezultati.


## Tema projekta

Tema projekta je analiza ponude evropskih restorana iz dve poslovne perspektive:

- turisticka organizacija, kojoj su vazni gradovi, tipovi kuhinja, dijetetske
  opcije, ocene i kvalitet ponude;
- investitor, kome su vazni trzista sa dobrim potencijalom, cenovni rang,
  popularne oznake, karakteristike uspesnih restorana i prostori za ulaganje.


## Sta je uradjeno

U projektu je najpre napravljena pocetna sema podataka, oznacena kao V1.
Nad V1 semom je definisano 10 upita i izmereno je njihovo vreme izvrsavanja. 
Ti rezultati predstavljaju pocetno stanje, tj. pre optimizacije.

Zatim je napravljena optimizovana V2 sema. Ona predstavlja skup namenski pripremljenih 
analitickih kolekcija, a zatim su na te kolekcije dodati indeksi. 

Na kraju su uporedene performanse V1 i V2 upita, a rezultati upita su
pripremljeni za vizualizaciju u Metabase-u.

## Model podataka

Pocetna V1 sema koristi cetiri kolekcije:

- restaurants - osnovni podaci o restoranima;
- restaurant_locations - podaci o drzavi, gradu i adresi;
- restaurant_ratings - ocene, broj recenzija i rangiranje;
- restaurant_classifications - kuhinje, cenovni rang, dijetetske opcije,
  oznake i dodatne karakteristike.

Optimizovana V2 sema koristi cetiri izvedene analiticke kolekcije:

- city_offer_stats - agregirani pokazatelji ponude po gradovima;
- city_cuisine_stats - pokazatelji zastupljenosti kuhinja po gradovima;
- classification_signal_stats - analiza oznaka, karakteristika i cenovnih
  rangova;
- cuisine_quality_stats - kvalitet i ocene po tipovima kuhinje.


## Performanse

Pre optimizacije, V1 upiti su se izvrsavali nad punim skupom podataka i trajali
su od oko 10 do preko 100 sekundi, u zavisnosti od broja dokumenata koji ucestvuju
u upitu i slozenosti agregacije.

Posle restruktuiranja seme i dodavanja indeksa, V2 upiti se izvrsavaju za manje
od jedne sekunde. Najveci dobitak dolazi iz toga sto se najskuplje operacije
vise ne ponavljaju pri svakom pokretanju upita, vec se koriste unapred
pripremljene analiticke kolekcije i odgovarajuci indeksi.

