# beegen/security/crypto_box.py
import os, json, base64
from typing import Dict, Any
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # type: ignore
from cryptography.hazmat.primitives import hashes  # type: ignore
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class Crypto:
    """
    Minimal symmetric encryption box using AES-GCM-256.

    - Derives a 32-byte key from a passphrase and a random salt via PBKDF2-HMAC-SHA256.
    - Uses a per-message random nonce.
    - Returns/accepts a tiny JSON-serializable dict (salt/nonce/ct are base64 strings).
    """

    def __init__(self, passphrase: str):
        """
        Args:
            passphrase: Secret passphrase used for key derivation.
        """
        if not passphrase:
            raise ValueError("passphrase must not be empty")
        self._secret = passphrase.encode("utf-8")

    def _key(self, salt: bytes) -> bytes:
        """Derive a 32-byte AES key from secret + salt."""
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000)
        return kdf.derive(self._secret)

    def encrypt(self, data: Dict[str, Any]) -> Dict[str, str]:
        """
        Encrypt a dict to a compact bundle.

        Returns:
            {"salt": b64, "nonce": b64, "ct": b64}
        """
        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = self._key(salt)
        pt = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ct = AESGCM(key).encrypt(nonce, pt, None)
        b64 = lambda b: base64.b64encode(b).decode("ascii")
        return {"salt": b64(salt), "nonce": b64(nonce), "ct": b64(ct)}

    def decrypt(self, bundle: Dict[str, str]) -> Dict[str, Any]:
        """
        Decrypt a bundle produced by `encrypt` back to a dict.
        """
        b64d = lambda s: base64.b64decode(s.encode("ascii"))
        salt, nonce, ct = b64d(bundle["salt"]), b64d(bundle["nonce"]), b64d(bundle["ct"])
        key = self._key(salt)
        pt = AESGCM(key).decrypt(nonce, ct, None)
        return json.loads(pt.decode("utf-8"))

    @staticmethod
    def looks_encrypted(obj: Any) -> bool:
        """Heuristic check for an encrypted bundle."""
        return isinstance(obj, dict) and all(k in obj for k in ("salt", "nonce", "ct"))

def main():
    # from beegen.configs.storage.mongo_config import MongoConfig
    # from beegen.loggings.loggers import LOGGER  # type: ignore
    # from pymongo import MongoClient

    # _mongo_client = MongoClient(MongoConfig.default().uri)
    # _mongo_db = _mongo_client[MongoConfig.default().authen_source]
    # _mongo_collection = _mongo_db["beegen_resource_configs_encrypt"]
    # old_secret = ""
    # old_box = Crypto(old_secret) if old_secret else None
    # new_box = Crypto(os.getenv("BEEGEN_RESOURCE_HUB_SECRET"))

    # updated = 0
    # for doc in _mongo_collection.find({}):
    #     _id = doc["_id"]

    #     # get plaintext dict
    #     if "enc" in doc and doc["enc"] is not None:
    #         if not old_box:
    #             LOGGER.error("Doc %s is encrypted but no old_secret supplied", _id)
    #             continue
    #         try:
    #             cfg = old_box.decrypt(doc["enc"])
    #         except Exception as e:
    #             LOGGER.error("Skip %s: cannot decrypt with old_secret (%s)", _id, e)
    #             continue
    #     else:
    #         cfg = doc.get("config_data")
    #         if cfg is None:
    #             continue

    #     # write back encrypted with new_secret
    #     _mongo_collection.replace_one(
    #         {"_id": _id},
    #         {
    #             "_id": _id,
    #             "config_type": doc.get("config_type"),
    #             "config_class": doc.get("config_class"),
    #             "enc": new_box.encrypt(cfg),
    #         },
    #         upsert=True,
    #     )
    #     updated += 1

    # # switch runtime secret so future reads/writes use the new key
    # LOGGER.info("Key rotation done: %d documents updated", updated)
    ###################################################
    bundle = {
    "salt": "CVBGdboGc/3onJw2lQlGUw==",
    "nonce": "ybc7tle6+sJBJZYR",
    "ct": "UuPh/4rOZL+Pe61ZaNuFKkUA8kOEx9cERIEfZFHJt/9zvIx8vdjeWYyInJM41gVpqU244pCST05k0fV0U1b9pXIPaYe+YNwgZGMtjJa3I5S6b/6DvwHBZaQeoAzQklFrPHvQS++XXCamiCaYxGSU6GS2OyA7J4RunmPtFBt5F8LERfgfRjiAN0Bd32ROnmlGJce8U/0xEbkNyPIYcz/lG3+0HrR2kv8f+gRN2tXRqmeHD1Lif2vNAz5XmVnaOIjpa2NFwtMwi30RmT4="
  }
    crypto = Crypto(os.getenv("BEEGEN_RESOURCE_HUB_SECRET"))
    results = crypto.decrypt(bundle)
    # results = crypto.encrypt(bundle)

    print(json.dumps(results))

if __name__ == "__main__":
    main()