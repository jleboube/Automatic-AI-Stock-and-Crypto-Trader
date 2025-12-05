#!/usr/bin/env python3
"""
Generate ED25519 keypair for Robinhood Crypto API

Instructions:
1. Run this script: python generate_robinhood_keys.py
2. Copy the PUBLIC KEY and register it with Robinhood at https://robinhood.com/account/crypto
3. Robinhood will give you an API KEY (starts with "rh-api-...")
4. Put BOTH the API KEY from Robinhood AND the PRIVATE KEY from this script in your .env file

Your .env should have:
ROBINHOOD_API_KEY=rh-api-xxxxx (from Robinhood after registering public key)
ROBINHOOD_PRIVATE_KEY=xxxxx (the private key printed below)
"""

import nacl.signing
import base64

# Generate an Ed25519 keypair
private_key = nacl.signing.SigningKey.generate()
public_key = private_key.verify_key

# Convert keys to base64 strings
private_key_base64 = base64.b64encode(private_key.encode()).decode()
public_key_base64 = base64.b64encode(public_key.encode()).decode()

print("=" * 60)
print("ROBINHOOD CRYPTO API KEY GENERATION")
print("=" * 60)
print()
print("STEP 1: Copy this PUBLIC KEY and register it with Robinhood:")
print("-" * 60)
print(f"PUBLIC KEY (Base64): {public_key_base64}")
print("-" * 60)
print()
print("STEP 2: Robinhood will give you an API KEY (starts with 'rh-api-...')")
print()
print("STEP 3: Add BOTH keys to your .env file:")
print("-" * 60)
print(f"ROBINHOOD_API_KEY=<the rh-api-xxx key from Robinhood>")
print(f"ROBINHOOD_PRIVATE_KEY={private_key_base64}")
print("-" * 60)
print()
print("IMPORTANT: Keep the private key secret! Never share it.")
print("=" * 60)
