# Resepti-importteri

Etusivulta voi tuoda verkkoreseptin URL-osoitteella tai lukea yhden
reseptikuvan paikallisella OCR:llä. Kuvatuonti hyväksyy JPEG- ja PNG-kuvat,
joiden koko on enintään 10 Mt ja 20 megapikseliä. Tunnistettua tekstiä ja
siitä jäsennettyjä reseptikenttiä voi korjata esikatselussa.

Kuvareseptien tallennus Grocyyn ei ole vielä käytettävissä. Esikatselun
tietoja ei säilytetä, kun sivulta poistutaan. URL-tuonti toimii ennallaan.

Kuvien lukeminen tarvitsee Tesseractin suomen ja englannin kieliaineistoineen
sekä Pythonin Pillow- ja pytesseract-paketit. Ne sisältyvät Dockerfileen;
päivitä kuva rakentamalla kontti uudelleen.
