from sheetsapi import config

config.Config.init()

from sheetsapi import envelope_encryption


def test_encryption_end_to_end():
    my_token = "this is so secret pls keep it safe im trusting you"
    enc = envelope_encryption.EnvelopeEncryption.encrypt(my_token)
    dec = envelope_encryption.EnvelopeEncryption.decrypt(
        encrypted_data_b64=enc.encrypted_data,
        encrypted_key_b64=enc.encrypted_key,
        context=enc.context
    )
    assert my_token == dec

    # soke test caching works when a key should be in the cache
    dec = envelope_encryption.EnvelopeEncryption.decrypt(
        encrypted_data_b64=enc.encrypted_data,
        encrypted_key_b64=enc.encrypted_key,
        context=enc.context
    )
    assert my_token == dec
