from src.data_agents.paper.title_cleaner import clean_paper_title


def test_clean_paper_title_strips_mathml_and_preserves_formula_tokens():
    raw = """Manipulation of valley pseudospin in <mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML"><mml:msub><mml:mi>WSe</mml:mi><mml:mn>2</mml:mn></mml:msub><mml:mo>/</mml:mo><mml:msub><mml:mi>CrI</mml:mi><mml:mn>3</mml:mn></mml:msub></mml:math> heterostructures by the magnetic proximity effect"""

    assert clean_paper_title(raw) == "Manipulation of valley pseudospin in WSe2/CrI3 heterostructures by the magnetic proximity effect"


def test_clean_paper_title_decodes_entities_and_sub_sup_tags():
    raw = "First-principles study of Ga-vacancy induced magnetism in β-Ga<sub>2</sub>O<sub>3</sub> &amp; related systems"

    assert clean_paper_title(raw) == "First-principles study of Ga-vacancy induced magnetism in β-Ga2O3 & related systems"


def test_clean_paper_title_compacts_formula_tokens_from_mathml_runs():
    raw = """Quasiparticle electronic structure of honeycomb <mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML"><mml:mi>C</mml:mi><mml:mn>3</mml:mn><mml:mi>N</mml:mi></mml:math>: from monolayer to bulk"""

    assert clean_paper_title(raw) == "Quasiparticle electronic structure of honeycomb C3N: from monolayer to bulk"


def test_clean_paper_title_compacts_plaintext_formula_tokens():
    raw = "Quasiparticle electronic structure of honeycomb C 3 N: from monolayer to bulk"

    assert clean_paper_title(raw) == "Quasiparticle electronic structure of honeycomb C3N: from monolayer to bulk"
