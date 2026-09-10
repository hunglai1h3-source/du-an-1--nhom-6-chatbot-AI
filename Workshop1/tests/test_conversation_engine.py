"""
Unit and Integration Tests for Phase 2: Medical Conversation State Engine.
"""
import unittest
import json
from unittest.mock import patch, MagicMock

import database

# Mock database connection before app initialization
mock_conn = MagicMock()
mock_conn.execute.return_value.fetchone.return_value = None
mock_conn.execute.return_value.fetchall.return_value = []
mock_conn.execute.return_value.lastrowid = 1
database.get_connection = MagicMock(return_value=mock_conn)

from app import app, load_conversation_state_from_db, save_conversation_state_to_db
from conversation_engine import (
    ConversationStage,
    NextAction,
    MedicalSlots,
    MedicalConversationState,
    extract_duration,
    extract_pain_scale,
    extract_fever,
    extract_location,
    extract_chief_complaint,
    detect_explicit_topic_change,
    detect_user_correction,
    process_conversation_turn,
    format_conversation_state_for_prompt,
    enforce_single_question_output,
)
from medical_safety import RiskLevel, check_medical_safety


class TestConversationEngineV2(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True

    def test_01_basic_flow_chief_complaint_and_stage(self):
        """31. Basic flow: 'Tôi đau bụng.' -> lưu chief_complaint, chuyển sang EXPLORATION, chọn 1 câu hỏi."""
        state = MedicalConversationState(conversation_id="test_conv_1")
        new_state = process_conversation_turn("Tôi đau bụng", state)

        self.assertEqual(new_state.slots.chief_complaint, "đau bụng")
        self.assertEqual(new_state.stage, ConversationStage.EXPLORATION.value)
        self.assertEqual(new_state.next_action, NextAction.ASK_QUESTION.value)
        self.assertIsNotNone(new_state.last_question_slot)
        # Mục tiêu kế tiếp phải là vị trí hoặc thời gian, không hỏi lại chief_complaint
        self.assertIn(new_state.last_question_slot, ["symptom_location", "duration"])
        self.assertIn("chief_complaint", new_state.collected_slots)

    def test_02_multi_slot_extraction_in_single_message(self):
        """32. Multi-slot: 'Tôi đau bụng dưới bên phải 3 ngày rồi, đau khoảng 7/10.' -> trích xuất cùng lúc location, duration, pain_scale."""
        state = MedicalConversationState(conversation_id="test_conv_2")
        message = "Tôi đau bụng dưới bên phải 3 ngày rồi, đau khoảng 7/10"
        new_state = process_conversation_turn(message, state)

        self.assertIn("đau bụng", new_state.slots.chief_complaint)
        self.assertEqual(new_state.slots.symptom_location, "bụng dưới bên phải")
        self.assertEqual(new_state.slots.duration, "3 ngày")
        self.assertEqual(new_state.slots.pain_scale, 7)

        # Các slot này phải nằm trong collected_slots
        self.assertIn("duration", new_state.collected_slots)
        self.assertIn("symptom_location", new_state.collected_slots)
        self.assertIn("pain_scale", new_state.collected_slots)

        # Câu hỏi tiếp theo KHÔNG được hỏi lại duration, location, hay pain_scale
        self.assertNotIn(new_state.last_question_slot, ["duration", "symptom_location", "pain_scale"])

    def test_03_no_repeat_question_across_turns(self):
        """33. No repeat: Bot đã thu thập duration thì các lượt sau không hỏi lại duration."""
        state = MedicalConversationState(conversation_id="test_conv_3")
        state.slots.chief_complaint = "đau đầu"
        state.slots.duration = "3 ngày"
        state.collected_slots = ["chief_complaint", "duration"]
        state.asked_slots = ["duration"]

        new_state = process_conversation_turn("Đau mức độ vừa phải thôi", state)
        self.assertNotEqual(new_state.last_question_slot, "duration")
        self.assertNotEqual(new_state.last_question_slot, "chief_complaint")

    def test_04_profile_data_reuse(self):
        """34. Profile data: selected_profile đã có age=19, sex='Nam' -> nạp vào slots, không hỏi lại tuổi/giới tính."""
        state = MedicalConversationState(conversation_id="test_conv_4")
        profile = {
            "age": 19,
            "sex": "Nam",
            "allergies": "hải sản",
            "medical_notes": "viêm dạ dày"
        }
        new_state = process_conversation_turn("Tôi bị đau họng", state, profile=profile)

        self.assertEqual(new_state.slots.age, 19)
        self.assertEqual(new_state.slots.gender, "Nam")
        self.assertIn("hải sản", new_state.slots.allergies)
        self.assertIn("viêm dạ dày", new_state.slots.medical_conditions)

        self.assertIn("age", new_state.collected_slots)
        self.assertIn("gender", new_state.collected_slots)
        self.assertNotEqual(new_state.last_question_slot, "age")
        self.assertNotEqual(new_state.last_question_slot, "gender")

    def test_05_assessment_ready_transition(self):
        """35. Assessment ready: Khi đã có đủ triệu chứng chính + vị trí + thời gian + mức độ -> assessment_ready = True, chuyển sang ASSESS."""
        state = MedicalConversationState(conversation_id="test_conv_5")
        state.slots.chief_complaint = "đau bụng"
        state.slots.symptom_location = "vùng quanh rốn"
        state.slots.duration = "2 ngày"
        state.slots.pain_scale = 5
        state.turn_count = 2

        new_state = process_conversation_turn("Không bị sốt, hơi đầy bụng", state)
        self.assertTrue(new_state.assessment_ready)
        self.assertEqual(new_state.stage, ConversationStage.ASSESSMENT.value)
        self.assertEqual(new_state.next_action, NextAction.ASSESS.value)

    def test_06_safety_interrupt_priority(self):
        """36. Safety interrupt: Dù Conversation Engine đang theo dõi, tin nhắn EMERGENCY vẫn được Safety Gate ngắt ngay lập tức."""
        # Giả lập hội thoại đang diễn ra
        history = [
            {"role": "user", "content": "Tôi bị đau bụng"},
            {"role": "assistant", "content": "Bạn bị đau ở vị trí nào của bụng?"}
        ]
        urgent_msg = "Giờ tôi không thở được"
        safety_res = check_medical_safety(urgent_msg, recent_history=history)

        self.assertEqual(safety_res.risk_level, RiskLevel.EMERGENCY)
        self.assertTrue(safety_res.should_stop_normal_flow)
        # Luồng khẩn cấp phải ngắt tại Safety Gate, không chạy Conversation Engine tiếp

    def test_07_topic_change_preserves_profile_resets_symptoms(self):
        """37. Topic change: 'Thôi bỏ đau bụng đi, tôi muốn hỏi về đau đầu' -> reset triệu chứng đau bụng, đổi topic, giữ profile."""
        state = MedicalConversationState(conversation_id="test_conv_7")
        state.slots.chief_complaint = "đau bụng"
        state.slots.symptom_location = "bụng dưới"
        state.slots.duration = "3 ngày"
        state.slots.age = 25
        state.slots.gender = "Nữ"
        state.current_topic = "đau bụng"

        message = "Thôi bỏ chuyện đau bụng đi, giờ tôi muốn hỏi về đau đầu"
        new_state = process_conversation_turn(message, state)

        self.assertEqual(new_state.slots.chief_complaint, "đau đầu")
        self.assertEqual(new_state.current_topic, "đau đầu")
        self.assertIn("đau bụng", new_state.previous_topics)
        # Triệu chứng cũ phải được làm sạch
        self.assertIsNone(new_state.slots.symptom_location)
        self.assertIsNone(new_state.slots.duration)
        # Nhưng thông tin nhân thân được giữ nguyên
        self.assertEqual(new_state.slots.age, 25)
        self.assertEqual(new_state.slots.gender, "Nữ")

    def test_08_user_correction_handling(self):
        """38. User correction: 'Tôi đau 5 ngày' -> sau đó 'À không, mới 2 ngày thôi' -> duration cập nhật thành '2 ngày'."""
        state = MedicalConversationState(conversation_id="test_conv_8")
        state.slots.chief_complaint = "đau lưng"
        state.slots.duration = "5 ngày"

        correction_msg = "À không, mới 2 ngày thôi"
        new_state = process_conversation_turn(correction_msg, state)

        self.assertEqual(new_state.slots.duration, "2 ngày")

    def test_09_multiple_conversations_isolation(self):
        """39. Multiple conversations: State của Conversation A và B hoàn toàn độc lập."""
        state_a = MedicalConversationState(conversation_id="conv_user1_headache")
        process_conversation_turn("Tôi bị đau đầu 2 ngày", state_a)

        state_b = MedicalConversationState(conversation_id="conv_user1_stomach")
        process_conversation_turn("Tôi bị đau bụng dưới", state_b)

        self.assertEqual(state_a.slots.chief_complaint, "đau đầu")
        self.assertEqual(state_a.slots.duration, "2 ngày")
        self.assertIsNone(state_a.slots.symptom_location)

        self.assertIn("đau bụng", state_b.slots.chief_complaint)
        self.assertEqual(state_b.slots.symptom_location, "bụng dưới")
        self.assertIsNone(state_b.slots.duration)

    def test_10_clear_and_new_chat_state_reset(self):
        """40. Clear / New chat: Reset state hoàn toàn sạch sẽ."""
        state = MedicalConversationState(conversation_id="conv_active")
        state.slots.chief_complaint = "đau ngực"
        state.slots.duration = "1 ngày"
        state.stage = ConversationStage.EXPLORATION.value

        # Khi tạo conversation mới / reset
        clean_state = MedicalConversationState(conversation_id="conv_new")
        self.assertEqual(clean_state.stage, ConversationStage.INITIAL.value)
        self.assertIsNone(clean_state.slots.chief_complaint)
        self.assertEqual(clean_state.collected_slots, [])

    def test_11_malformed_json_fallback_tolerance(self):
        """41. Malformed JSON: Dữ liệu state corrupt trong DB -> fallback sang state mới, không crash."""
        corrupted_mock_conn = MagicMock()
        corrupted_mock_conn.execute.return_value.fetchone.return_value = {
            "state_json": "{invalid json: true, bad: 'syntax'}"
        }
        state = load_conversation_state_from_db(corrupted_mock_conn, "corrupt_conv")
        self.assertIsNotNone(state)
        self.assertEqual(state.conversation_id, "corrupt_conv")
        self.assertEqual(state.stage, ConversationStage.INITIAL.value)

    def test_12_one_question_output_guard(self):
        """43. One question guard: Nếu model sinh 3 câu hỏi dồn dập, guard chỉ giữ đúng 1 câu hỏi chính."""
        raw_model_reply = (
            "Chào bạn, tôi rất tiếc khi biết bạn đang không khỏe. "
            "Bạn đau ở vị trí nào của bụng? "
            "Bạn bị đau bao lâu rồi? "
            "Bạn có bị sốt không?"
        )
        safe_reply = enforce_single_question_output(raw_model_reply, NextAction.ASK_QUESTION.value)

        # Số dấu hỏi trong kết quả cuối cùng phải bằng 1
        self.assertEqual(safe_reply.count("?"), 1)
        self.assertIn("Bạn đau ở vị trí nào", safe_reply)
        self.assertNotIn("Bạn bị đau bao lâu rồi?", safe_reply)
        self.assertNotIn("Bạn có bị sốt không?", safe_reply)

    def test_13_endpoint_chat_conversation_state_integration(self):
        """Integration: POST /chat nạp và trả về metadata của Conversation State Engine."""
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Tôi hiểu bạn đang đau bụng. Bạn đau ở vị trí nào của bụng?"
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=15, completion_tokens=25)

        with patch("app.create_chat_completion_with_retry", return_value=mock_response):
            res = self.client.post(
                "/chat",
                data={
                    "message": "Tôi bị đau bụng",
                    "conversation_id": "test_e2e_conv_1"
                },
                content_type="multipart/form-data"
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertIn("conversation_stage", data)
            self.assertIn("next_action", data)
            self.assertEqual(data["conversation_id"], "test_e2e_conv_1")
            self.assertEqual(data["conversation_stage"], ConversationStage.EXPLORATION.value)
            self.assertEqual(data["next_action"], NextAction.ASK_QUESTION.value)

    def test_14_endpoint_chat_reset(self):
        """Integration: POST /chat/reset xóa sạch trạng thái của conversation_id."""
        res = self.client.post(
            "/chat/reset",
            json={"conversation_id": "test_e2e_conv_1"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("status"), "success")


if __name__ == "__main__":
    unittest.main()
