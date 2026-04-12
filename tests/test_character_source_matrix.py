from player_wiki.character_source_matrix import DEFAULT_NATIVE_SOURCE_MATRIX_POLICY, NativeSourceMatrixPolicy


def test_default_native_source_matrix_policy_keeps_current_source_boundary_explicit():
    assert DEFAULT_NATIVE_SOURCE_MATRIX_POLICY.supports_base_class_identity(
        class_name="Wizard",
        class_source="PHB",
    )
    assert DEFAULT_NATIVE_SOURCE_MATRIX_POLICY.supports_base_class_identity(
        class_name="Artificer",
        class_source="tce",
    )
    assert not DEFAULT_NATIVE_SOURCE_MATRIX_POLICY.supports_base_class_identity(
        class_name="Mystic",
        class_source="ua",
    )
    assert not DEFAULT_NATIVE_SOURCE_MATRIX_POLICY.supports_base_class_identity(
        class_name="Expert Sidekick",
        class_source="TCE",
    )
    assert DEFAULT_NATIVE_SOURCE_MATRIX_POLICY.supports_subclass_source("XGE")
    assert DEFAULT_NATIVE_SOURCE_MATRIX_POLICY.supports_subclass_source("DMG")
    assert not DEFAULT_NATIVE_SOURCE_MATRIX_POLICY.supports_subclass_source("ERLW")
    assert DEFAULT_NATIVE_SOURCE_MATRIX_POLICY.should_prefix_profile_link_source("SCAG")
    assert not DEFAULT_NATIVE_SOURCE_MATRIX_POLICY.should_prefix_profile_link_source("PHB")


def test_native_source_matrix_policy_can_enable_future_source_via_policy_only():
    future_policy = NativeSourceMatrixPolicy(
        supported_non_phb_base_class_keys=frozenset({("erlw", "Artificer")}),
        supported_subordinate_source_ids=frozenset({"xge"}),
    )

    assert future_policy.supports_base_class_identity(class_name="Artificer", class_source="ERLW")
    assert future_policy.supports_subclass_source("ERLW")
    assert future_policy.should_prefix_profile_link_source("ERLW")
    assert future_policy.source_label("erlw") == "ERLW"
    assert future_policy.supported_non_phb_source_ids == frozenset({"ERLW", "XGE"})
