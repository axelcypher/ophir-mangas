# Ophir Mangas

A self-hosted collection manager for manga: a catalogue shared by every account of an instance, and each account's copies, reading, wishlists and preorders. The German words are the ones the interface shows.

## Catalogue

**Catalogue** (Katalog):
Every series, edition and volume known to the instance, shared by all its accounts.
_Avoid_: database, library

**Series** (Reihe):
A manga work as a whole, independent of who publishes it in which language.
_Avoid_: title, work, franchise

**Edition** (Ausgabe):
One publication of a series by one publisher in one language and format, with its own volume numbering (Carlsen's German Attack on Titan, the Japanese Kodansha original, a Perfect Edition).
_Avoid_: version, release, print

**Volume** (Band):
One book of an edition, identified by its number within the edition and its ISBN.
_Avoid_: book, issue, tankōbon

**Variant** (Variante):
A volume sold in another form under the same number as the standard one, such as a Limited Edition with extras; it has an ISBN of its own.
_Avoid_: special edition (that is an Edition)

**Special volume** (Sonderband):
A volume of an edition without a number, such as a fanbook or guide.
_Avoid_: extra, bonus volume

**Publisher** (Verlag):
The company that publishes an edition.

**Demographic** (Zielgruppe):
The readership a series is published for: Shōnen, Seinen, Shōjo, Josei or Kodomo.
_Avoid_: genre

**List price** (Listenpreis):
The price the publisher sells a volume for.
_Avoid_: MSRP, retail price, cover price

**Market value** (Marktwert):
What a volume is worth second-hand, as someone last recorded it; only kept for volumes where it matters.
_Avoid_: price, value

## An account's manga

**Copy** (Exemplar):
A physical volume an account owns.
_Avoid_: item, entry, book

**Condition** (Zustand):
The state of a copy: New/sealed (Neu/OVP), Very good (Sehr gut), With reading marks (Mit Lesespuren) or Damaged (Beschädigt).
_Avoid_: "Gelesen" for a condition

**First printing** (Erstauflage):
A copy from the first print run of its volume.

**Collecting** (Sammle ich):
An account's statement that it collects an edition; only ever set by hand.
_Avoid_: following, subscribing

**Gap** (Lücke):
A volume number of an edition the account is collecting that has been released and that the account owns in no variant.
_Avoid_: missing volume (for volumes merely not owned)

**Release calendar** (Neuerscheinungen):
The coming volumes of the editions an account is collecting, by month.

**Read** (Gelesen):
That an account has read a volume, whether it owns a copy or not.

**Reading status** (Lesestatus):
Where an account stands with a series: planned (Geplant), reading (Lese ich), paused (Pausiert), dropped (Abgebrochen) or finished (Fertig).
_Avoid_: progress (that is the count of read volumes)

**Wishlist** (Wunschliste):
A named list of volumes or whole editions an account wants; every account has a default one.
_Avoid_: watchlist

**Preorder** (Vorbestellung):
A volume ordered before its release, followed from the order until its copies arrive.
