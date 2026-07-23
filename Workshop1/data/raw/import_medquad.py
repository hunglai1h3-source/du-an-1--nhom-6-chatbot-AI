import csv
import os
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDQUAD_PATH = os.path.join(BASE_DIR, "MedQuAD-master")
OUTPUT_CSV = os.path.join(BASE_DIR, "medquad.csv")


def clean_text(text):
    if not text:
        return ""
    return " ".join(text.split())


def main():
    if not os.path.isdir(MEDQUAD_PATH):
        print("Không tìm thấy thư mục:")
        print(MEDQUAD_PATH)
        return

    xml_count = 0
    qa_count = 0
    error_count = 0

    with open(
        OUTPUT_CSV,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "question",
                "answer",
                "category",
                "source"
            ]
        )

        writer.writeheader()

        for root_dir, _, files in os.walk(MEDQUAD_PATH):

            for file_name in files:

                if not file_name.lower().endswith(".xml"):
                    continue

                xml_count += 1
                file_path = os.path.join(root_dir, file_name)

                try:
                    tree = ET.parse(file_path)
                    root = tree.getroot()

                    for qa_pair in root.findall(".//QAPair"):

                        question_element = qa_pair.find("Question")
                        answer_element = qa_pair.find("Answer")

                        question = ""
                        answer = ""

                        if question_element is not None:
                            question = clean_text(
                                " ".join(question_element.itertext())
                            )

                        if answer_element is not None:
                            answer = clean_text(
                                " ".join(answer_element.itertext())
                            )

                        if question and answer:
                            writer.writerow({
                                "question": question,
                                "answer": answer,
                                "category": os.path.basename(root_dir),
                                "source": "MedQuAD"
                            })

                            qa_count += 1

                    if xml_count % 500 == 0:
                        print(
                            f"Đã xử lý {xml_count} file XML, "
                            f"thu được {qa_count} câu hỏi..."
                        )

                except ET.ParseError as error:
                    error_count += 1
                    print(f"Lỗi XML: {file_path}")
                    print(error)

                except OSError as error:
                    error_count += 1
                    print(f"Lỗi mở file: {file_path}")
                    print(error)

                except Exception as error:
                    error_count += 1
                    print(f"Lỗi khác: {file_path}")
                    print(error)

    print("=" * 50)
    print("Đã hoàn thành!")
    print("Số file XML:", xml_count)
    print("Số câu hỏi - trả lời:", qa_count)
    print("Số file lỗi:", error_count)
    print("File kết quả:")
    print(OUTPUT_CSV)
    print("=" * 50)


if __name__ == "__main__":
    main()