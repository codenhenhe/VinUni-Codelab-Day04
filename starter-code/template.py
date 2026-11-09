"""
Lab #4: System Prompt Engineering & Tool Calling Engine
Học viên hoàn thiện các mục TODO để hoàn thành bài lab.

Kiến trúc:
  - ChatbotBaseline: LLM thuần, không dùng tool → quan sát hallucination.
  - ToolCallingAgent: Agent dùng System Prompt + 2 Tool Schemas.
"""

import json
import re
from typing import Dict, Any, List
from tools import TOOL_DEFINITIONS, TOOL_MAP, search_product_catalog, submit_support_ticket

# ═══════════════════════════════════════════════════════════════════════════
# TODO 1: Thiết kế SYSTEM PROMPT cấp sản xuất
# Yêu cầu: Phải chứa Persona, Core Rules, Operational Boundaries, Output Contract.
# ═══════════════════════════════════════════════════════════════════════════


SYSTEM_PROMPT = """
Bạn là VinAssistant – trợ lý AI chính thức của hệ sinh thái Vingroup.

## 1. PERSONA
- Vai trò: Tư vấn sản phẩm, dịch vụ Vingroup (VinFast, Vinpearl).
- Phong cách: Chuyên nghiệp, thân thiện, chính xác và ngắn gọn.
- Không bịa đặt thông tin.

## 2. AVAILABLE TOOLS
{tools}

## 3. CORE RULES
1. Khi khách hỏi thông tin sản phẩm, giá hoặc tìm kiếm sản phẩm, PHẢI gọi `search_product_catalog`. Không tự bịa giá, tính năng hoặc thông tin sản phẩm.
2. Khi khách yêu cầu tạo ticket hỗ trợ, PHẢI gọi `submit_support_ticket`. Không tự tạo ticket_id.
3. Với câu hỏi FAQ, trả lời trực tiếp nếu có đủ thông tin đáng tin cậy, không cần gọi tool.
4. Nếu cần nhiều tool, gọi lần lượt từng tool rồi tổng hợp kết quả.
5. Chỉ xác nhận thao tác thành công khi có kết quả xác nhận từ tool.

## 4. OPERATIONAL BOUNDARIES
- Chỉ hỗ trợ các vấn đề thuộc hệ sinh thái Vingroup.
- Không tự suy đoán chính sách, giá bán hoặc thông tin chưa được xác minh.
- Không thực hiện các giao dịch ngoài khả năng của tool.
- Nếu thiếu thông tin bắt buộc, hỏi khách hàng bổ sung.
- Nếu yêu cầu ngoài phạm vi, giải thích và hướng dẫn phù hợp.

## 5. OUTPUT CONTRACT
Tuân thủ quy trình:
- Thought: Xác định ý định và cách xử lý.
- Action: Gọi tool nếu cần.
- Observation: Kiểm tra kết quả tool.
- Final Answer: Trả lời khách hàng rõ ràng, ngắn gọn và dựa trên thông tin đã xác minh.
"""


# ═══════════════════════════════════════════════════════════════════════════
# CLASS: ChatbotBaseline
# ═══════════════════════════════════════════════════════════════════════════

class ChatbotBaseline:
    """Baseline LLM Chatbot — Không sử dụng Tool Calling hay ReAct Loop."""

    def query(self, user_input: str) -> Dict[str, Any]:
        # TODO 2: Trả về câu trả lời tĩnh (mock) hoặc gọi Gemini API 1 lượt (không dùng tool)
        # Mục tiêu: Quan sát hiện tượng bịa thông tin (hallucination)
        return {
            "answer": f"[Chatbot Baseline] Trả lời cho: {user_input}",
            "tool_calls": [],
            "status": "success",
            "mode": "mock_baseline"
        }


# ═══════════════════════════════════════════════════════════════════════════
# CLASS: ToolCallingAgent
# ═══════════════════════════════════════════════════════════════════════════

class ToolCallingAgent:
    """Agent với System Prompt Engineering & Tool Calling."""

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.trace: List[Dict[str, Any]] = []
    
    def run(self, user_input: str) -> Dict[str, Any]:
        self.trace = []
        self.trace.append({"step": "init", "user_input": user_input})

        text = user_input.lower()

        # TODO 3: Intent Detection
        intents = {
            "needs_catalog": any(k in text for k in [
                "xe điện", "tìm xe", "tìm sản phẩm", "giá",
                "bao nhiêu", "vinpearl", "du lịch"
            ]),
            "needs_ticket": any(k in text for k in [
                "bị lỗi", "gặp sự cố", "hỗ trợ", "khiếu nại",
                "tạo ticket", "báo lỗi"
            ]),
            "is_faq": any(k in text for k in [
                "bảo hành", "chính sách", "quy định", "là gì"
            ])
        }

        # FAQ về sản phẩm không đồng nghĩa với tìm kiếm sản phẩm
        if intents["is_faq"] and not intents["needs_ticket"]:
            intents["needs_catalog"] = False

        self.trace.append({
            "step": "intent_detection",
            "intents": intents
        })

        observations = []
        iteration = 0

        # Xác định tham số catalog
        category = (
            "du_lich" if any(k in text for k in ["du lịch", "vinpearl", "resort"])
            else "xe_dien"
        )

        price_match = re.search(
            r"(?:dưới|tối đa)\s*(\d+(?:[.,]\d+)?)\s*(triệu|tỷ)",
            text
        )

        max_price = 999999999999
        if price_match:
            value = float(price_match.group(1).replace(",", "."))
            max_price = int(value * (
                1_000_000 if price_match.group(2) == "triệu"
                else 1_000_000_000
            ))

        # FAQ: Trả lời trực tiếp, không gọi tool
        if intents["is_faq"] and not intents["needs_ticket"]:
            answer = (
                "VinFast có chính sách bảo hành pin 10 năm."
                if "bảo hành" in text and "pin" in text
                else "Vui lòng cung cấp thêm thông tin để được hỗ trợ chính xác."
            )

            self.trace.append({
                "step": "final_answer",
                "observation": answer
            })

            return {
                "answer": answer,
                "trace": self.trace,
                "iterations": 1,
                "status": "completed"
            }

        # Tool 1: Catalog
        if intents["needs_catalog"]:
            if iteration >= self.max_iterations:
                return {
                    "answer": "Lỗi: Vượt quá số bước tối đa.",
                    "trace": self.trace,
                    "iterations": iteration,
                    "status": "max_iterations_reached"
                }

            iteration += 1

            result = search_product_catalog(
                category=category,
                max_price=max_price
            )

            observations.append({
                "tool": "search_product_catalog",
                "result": result
            })

            self.trace.append({
                "step": f"iteration_{iteration}",
                "tool": "search_product_catalog",
                "observation": result
            })

        # Tool 2: Support Ticket
        if intents["needs_ticket"]:
            if iteration >= self.max_iterations:
                return {
                    "answer": "Lỗi: Vượt quá số bước tối đa.",
                    "trace": self.trace,
                    "iterations": iteration,
                    "status": "max_iterations_reached"
                }

            name_match = re.search(
                r"tôi tên\s+([^,.!]+)",
                user_input,
                re.IGNORECASE
            )
            customer_name = name_match.group(1).strip() if name_match else ""

            if customer_name:
                iteration += 1

                result = submit_support_ticket(
                    customer_name=customer_name,
                    issue_description=user_input,
                    priority="high" if any(
                        k in text for k in ["gấp", "khẩn cấp"]
                    ) else "medium"
                )
            else:
                result = "Thiếu tên khách hàng, chưa thể tạo ticket."

            observations.append({
                "tool": "submit_support_ticket",
                "result": result
            })

            self.trace.append({
                "step": f"iteration_{iteration}",
                "tool": "submit_support_ticket",
                "observation": result
            })

        # Tổng hợp Final Answer (không tăng iteration)
        answers = []

        for obs in observations:
            result = obs["result"]

            if obs["tool"] == "search_product_catalog":
                # Milestone 4.2: Empty Results Handling
                if not result or len(result) == 0:
                    answers.append(
                        "Rất tiếc, không tìm thấy sản phẩm phù hợp."
                    )
                else:
                    for p in result:
                        answers.append(
                            f"- {p['name']}: {p['price_vnd']:,} VNĐ. "
                            f"{p['description']}"
                        )

            elif obs["tool"] == "submit_support_ticket":
                if (
                    isinstance(result, dict)
                    and result.get("ticket_id", "").startswith("TK-")
                ):
                    answers.append(
                        f"Đã tạo ticket thành công cho khách hàng "
                        f"{customer_name}: {result['ticket_id']}."
                    )
                else:
                    answers.append(str(result))

        final_answer = "\n".join(answers) if answers else (
            "Bạn cần hỗ trợ về vấn đề gì thuộc hệ sinh thái Vingroup?"
        )

        self.trace.append({
            "step": "final_answer",
            "observation": observations,
            "final_answer": final_answer
        })

        return {
            "answer": final_answer,
            "trace": self.trace,
            "iterations": iteration,
            "status": "completed"
        }

    

# ═══════════════════════════════════════════════════════════════════════════
# MAIN — Chạy thử nhanh
# ═══════════════════════════════════════════════════════════════════════════

def main():
    user_query = "Tôi muốn xem xe điện VinFast giá dưới 600 triệu."

    print("=== RUNNING CHATBOT BASELINE ===")
    chatbot = ChatbotBaseline()
    print(chatbot.query(user_query))

    print("\n=== RUNNING TOOL CALLING AGENT ===")
    agent = ToolCallingAgent(max_iterations=5)
    result = agent.run(user_query)
    print("Result:", result["answer"])
    print("Trace Log:", json.dumps(agent.trace, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
