from pathlib import Path

from boamp.synthetic.pipeline import generate_clean_world, generate_observed_world

REPO = Path(__file__).resolve().parents[1]


def test_fixed_seed_gives_identical_row_counts():
    w1 = generate_clean_world("central_provisional", REPO, n_buyers=50, world_seed=555)
    w2 = generate_clean_world("central_provisional", REPO, n_buyers=50, world_seed=555)
    for key in ["buyers", "establishments", "needs", "cycles", "true_relations",
                "notice_family_membership", "clean_notices"]:
        assert len(w1[key]) == len(w2[key]), key


def test_fixed_seed_gives_byte_identical_key_columns():
    w1 = generate_clean_world("central_provisional", REPO, n_buyers=50, world_seed=555)
    w2 = generate_clean_world("central_provisional", REPO, n_buyers=50, world_seed=555)
    assert w1["buyers"]["siren_true"].tolist() == w2["buyers"]["siren_true"].tolist()
    assert w1["establishments"]["siret_true"].tolist() == w2["establishments"]["siret_true"].tolist()
    assert w1["clean_notices"]["objet_true"].tolist() == w2["clean_notices"]["objet_true"].tolist()
    assert w1["true_relations"]["relation_type"].tolist() == w2["true_relations"]["relation_type"].tolist()


def test_fixed_seed_corruption_is_also_reproducible():
    w = generate_clean_world("central_provisional", REPO, n_buyers=40, world_seed=777)
    obs1, log1 = generate_observed_world(w, "central_provisional", REPO, corruption_seed=888)
    obs2, log2 = generate_observed_world(w, "central_provisional", REPO, corruption_seed=888)
    assert obs1.equals(obs2)
    assert len(log1) == len(log2)


def test_different_world_seed_changes_the_generated_population():
    w1 = generate_clean_world("central_provisional", REPO, n_buyers=50, world_seed=1)
    w2 = generate_clean_world("central_provisional", REPO, n_buyers=50, world_seed=2)
    assert w1["buyers"]["siren_true"].tolist() != w2["buyers"]["siren_true"].tolist()
    assert w1["clean_notices"]["objet_true"].tolist() != w2["clean_notices"]["objet_true"].tolist()


def test_different_corruption_seed_changes_observed_notices():
    w = generate_clean_world("central_provisional", REPO, n_buyers=40, world_seed=333)
    obs1, _ = generate_observed_world(w, "central_provisional", REPO, corruption_seed=1)
    obs2, _ = generate_observed_world(w, "central_provisional", REPO, corruption_seed=2)
    assert not obs1["buyer_name_raw"].equals(obs2["buyer_name_raw"])


def test_world_seed_independent_of_corruption_seed():
    """Holding the world fixed while varying only the corruption seed must
    not change the clean world itself (spec: two independent seeds)."""
    w = generate_clean_world("central_provisional", REPO, n_buyers=30, world_seed=42)
    before = w["clean_notices"]["objet_true"].tolist()
    generate_observed_world(w, "central_provisional", REPO, corruption_seed=1)
    generate_observed_world(w, "central_provisional", REPO, corruption_seed=2)
    after = w["clean_notices"]["objet_true"].tolist()
    assert before == after
