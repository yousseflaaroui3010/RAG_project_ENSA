from scripts.corpus import MANIFEST


def test_cleiss_guide_uses_the_live_permanent_pdf_url():
    guide = next(
        document
        for document in MANIFEST
        if document.file_name == "cnss-regime-securite-sociale-cleiss.pdf"
    )

    assert guide.url == (
        "https://www.univ-tlse2.fr/medias/fichier/"
        "maroc-regime-de-securite-sociale-pour-salaries-version-n2_"
        "1418995412210-pdf"
    )
