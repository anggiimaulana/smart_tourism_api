from sqlalchemy import Enum as PgEnum


wilayah_enum = PgEnum(
    "Indramayu",
    "Cirebon",
    "Majalengka",
    "Kuningan",
    name="wilayah_enum",
)

status_enum = PgEnum(
    "aktif",
    "nonaktif",
    "draft",
    name="status_enum",
)

sentimen_enum = PgEnum(
    "positif",
    "negatif",
    "netral",
    name="sentimen_enum",
)

role_enum = PgEnum(
    "admin",
    "pengunjung",
    name="role_enum",
)

tipe_tempat_enum = PgEnum(
    "wisata",
    "kuliner",
    "nongkrong",
    name="tipe_tempat_enum",
)

jenis_kuliner_enum = PgEnum(
    "Restoran",
    "Warung",
    "Cafe",
    "Kedai",
    "Food Court",
    "Angkringan",
    "Lainnya",
    name="jenis_kuliner_enum",
)

kategori_wisata_enum = PgEnum(
    "Alam",
    "Buatan",
    "Budaya",
    "Religi",
    "Petualangan",
    "Edukasi",
    "Lainnya",
    name="kategori_wisata",
)

model_sentimen_enum = PgEnum(
    "indobert",
    "naive_bayes",
    "svm",
    "decision_tree",
    name="model_sentimen",
)
