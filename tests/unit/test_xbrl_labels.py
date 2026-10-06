from bdc_soi.xbrl_inventory import decode_label


def test_typed_member_labels_are_entity_decoded():
    # Stellus: typed members carry '&amp;' literally; the issuer became 'Bart amp; Associates LLC'.
    assert decode_label("Bart &amp; Associates LLC, B&amp;A Partners Holding LLC") == "Bart & Associates LLC, B&A Partners Holding LLC"
    assert decode_label("Plain &") == "Plain &"
