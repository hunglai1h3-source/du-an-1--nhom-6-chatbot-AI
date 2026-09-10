import unittest
import json
from io import BytesIO
from unittest.mock import patch, MagicMock
import database

# Mock database connection before app initializes PostgreSQL tables
mock_conn = MagicMock()
mock_conn.execute.return_value.fetchone.return_value = None
mock_conn.execute.return_value.fetchall.return_value = []
mock_conn.execute.return_value.lastrowid = 1
database.get_connection = MagicMock(return_value=mock_conn)

from app import app
from medical_safety import RiskLevel, SafetyCategory

class TestChatEndpointSafetyV2(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True

    def test_chat_emergency_text_fast_path(self):
        """Test emergency text triggers fast_path emergency response without AI call."""
        response = self.client.post(
            "/chat",
            data={"message": "Tôi không thở được"},
            content_type="multipart/form-data"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsNotNone(data)
        self.assertTrue(data.get("fast_path"))
        self.assertIn("emergency", data)
        self.assertEqual(data["emergency"].get("phone"), "115")
        self.assertEqual(data["emergency"].get("severity"), "critical")
        self.assertIn("115", data["reply"])
        self.assertEqual(data.get("safety_result", {}).get("risk_level"), RiskLevel.EMERGENCY.value)
        self.assertTrue(data.get("safety_result", {}).get("is_emergency"))
        self.assertEqual(data.get("safety_state", {}).get("highest_risk_level"), RiskLevel.EMERGENCY.value)

    def test_chat_emergency_text_with_image_attached_bug_fixed(self):
        """
        Critical regression test:
        Previous bug: if has_image was True, emergency text check was bypassed!
        V2 fix: Emergency text check MUST still trigger even when an image is attached.
        """
        fake_image = (BytesIO(b"fake image binary content"), "chest.jpg")
        response = self.client.post(
            "/chat",
            data={
                "message": "Tôi đau ngực dữ dội và ngất xỉu",
                "image": fake_image
            },
            content_type="multipart/form-data"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsNotNone(data)
        self.assertTrue(data.get("fast_path"), "Emergency bypass must trigger even when image is attached!")
        self.assertIn("emergency", data)
        self.assertEqual(data["emergency"].get("severity"), "critical")
        self.assertEqual(data.get("safety_result", {}).get("category"), SafetyCategory.CHEST_CARDIAC.value)
        self.assertTrue(data.get("safety_result", {}).get("is_emergency"))

    def test_chat_self_harm_endpoint(self):
        """Test suicidal / self-harm message triggers emergency fast path with crisis hotlines."""
        response = self.client.post(
            "/chat",
            data={"message": "Tôi muốn tự tử"},
            content_type="multipart/form-data"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsNotNone(data)
        self.assertTrue(data.get("fast_path"))
        self.assertIn("emergency", data)
        self.assertEqual(data.get("safety_result", {}).get("category"), SafetyCategory.SELF_HARM_IMMEDIATE.value)
        self.assertIn("115", data["reply"])
        self.assertEqual(data["emergency"].get("phone"), "115")

    def test_chat_normal_symptom_not_blocked_by_safety(self):
        """Normal symptom ('Tôi hơi đau bụng nhẹ') must NOT trigger emergency fast_path."""
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Bạn nên theo dõi thêm triệu chứng đau bụng nhẹ."
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)

        with patch("app.create_chat_completion_with_retry", return_value=mock_response):
            response = self.client.post(
                "/chat",
                data={"message": "Tôi hơi đau bụng nhẹ"},
                content_type="multipart/form-data"
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json() or {}
            self.assertFalse(data.get("fast_path", False), "Mild symptom should not trigger emergency fast_path")
            self.assertEqual(data.get("safety_result", {}).get("risk_level"), RiskLevel.CAUTION.value)
            self.assertFalse(data.get("safety_result", {}).get("is_emergency"))
            self.assertIn("đau bụng", data.get("reply", ""))

    def test_chat_state_escalation_across_turns(self):
        """Test sending safety_state from previous turn escalates to emergency on acute symptom."""
        prior_state = {
            "current_level": "CAUTION",
            "active_categories": ["POISONING_OVERDOSE"],
            "unresolved_flags": ["POTENTIAL_OVERDOSE"],
            "history_summary": ["Took pills earlier"]
        }
        response = self.client.post(
            "/chat",
            data={
                "message": "Bây giờ tôi bắt đầu co giật và khó thở",
                "safety_state": json.dumps(prior_state)
            },
            content_type="multipart/form-data"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("fast_path"))
        self.assertEqual(data.get("safety_result", {}).get("risk_level"), RiskLevel.EMERGENCY.value)

if __name__ == "__main__":
    unittest.main()
