"""Tests for AI feature engineering."""
import pytest
import numpy as np
from bot.ai.feature_engine import build_features, FEATURE_NAMES


class TestFeatureEngine:
    def test_feature_vector_size(self, sample_snapshot):
        """Feature vector should match FEATURE_NAMES length."""
        features = build_features(sample_snapshot)
        assert len(features) == len(FEATURE_NAMES)

    def test_feature_vector_is_numpy(self, sample_snapshot):
        features = build_features(sample_snapshot)
        assert isinstance(features, np.ndarray)

    def test_no_nan_values(self, sample_snapshot):
        """Features should not contain NaN."""
        features = build_features(sample_snapshot)
        assert not np.any(np.isnan(features))

    def test_no_inf_values(self, sample_snapshot):
        """Features should not contain infinity."""
        features = build_features(sample_snapshot)
        assert not np.any(np.isinf(features))

    def test_feature_names_defined(self):
        """All feature names should be non-empty strings."""
        for name in FEATURE_NAMES:
            assert isinstance(name, str)
            assert len(name) > 0

    def test_rsi_feature_in_range(self, sample_snapshot):
        """RSI feature should be between 0 and 100."""
        features = build_features(sample_snapshot)
        rsi_idx = FEATURE_NAMES.index("rsi_14")
        assert 0 <= features[rsi_idx] <= 100

    def test_volume_ratio_positive(self, sample_snapshot):
        """Volume ratio should be positive."""
        features = build_features(sample_snapshot)
        vol_idx = FEATURE_NAMES.index("volume_ratio")
        assert features[vol_idx] > 0
