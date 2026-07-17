def test_config_loads_and_paths_resolve(cfg):
    assert cfg.paths.raw_boamp_dir.is_absolute()
    assert cfg.pipeline.run.month_days == 30.44


def test_weights_sum_to_one(cfg):
    w = cfg.pipeline.scoring.weights
    assert abs(w.text + w.cpv + w.time + w.buyer - 1.0) < 1e-9


def test_thresholds_ordered_and_frozen(cfg):
    t = cfg.pipeline.thresholds
    assert t.broad < t.balanced < t.strict
    assert abs(t.balanced - 0.323022) < 1e-6


def test_survival_variants_include_window_6m(cfg):
    assert "window_6m" in cfg.pipeline.survival.variants
