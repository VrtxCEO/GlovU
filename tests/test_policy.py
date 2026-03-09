import json
import unittest

from glovu import policy


class PolicyRedactionTests(unittest.TestCase):
    def test_redact_body_skips_opaque_payloads(self) -> None:
        body = json.dumps({"ciphertext": "A" * 120})

        cleaned, fields = policy.redact_body(body)

        self.assertEqual(json.loads(cleaned)["ciphertext"], "A" * 120)
        self.assertEqual(fields, [])

    def test_redact_body_redacts_human_readable_pii(self) -> None:
        body = json.dumps({"message": "email me at test@example.com"})

        cleaned, fields = policy.redact_body(body)

        self.assertIn("[REDACTED BY GLOVE]", json.loads(cleaned)["message"])
        self.assertIn("email address", fields)


if __name__ == "__main__":
    unittest.main()
