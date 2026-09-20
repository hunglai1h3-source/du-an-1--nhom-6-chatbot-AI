#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MediCare AI — Admin & RBAC Bootstrap Tool
Idempotent, parameterized, secure CLI to grant administrative roles.
"""

import sys
import argparse
from database import get_connection
from rbac_service import (
    ROLE_SUPER_ADMIN,
    ROLE_ADMIN,
    ROLE_CONTENT_EDITOR,
    ROLE_MEDICAL_REVIEWER,
    ROLE_SUPPORT,
    ROLE_METADATA,
    normalize_role,
    log_admin_activity,
)

AVAILABLE_ROLES = [
    ROLE_SUPER_ADMIN,
    ROLE_ADMIN,
    ROLE_CONTENT_EDITOR,
    ROLE_MEDICAL_REVIEWER,
    ROLE_SUPPORT,
]


def bootstrap_admin(email, role_name=ROLE_SUPER_ADMIN, confirm=True):
    email = str(email or "").strip().lower()
    if not email:
        print("[LỖI] Vui lòng nhập email hợp lệ.")
        return False

    role = normalize_role(role_name)
    if role not in AVAILABLE_ROLES:
        print(f"[LỖI] Vai trò '{role_name}' không hợp lệ. Chọn một trong: {', '.join(AVAILABLE_ROLES)}")
        return False

    connection = get_connection()
    try:
        user = connection.execute(
            """
            SELECT id, full_name, email, role, is_active
            FROM users
            WHERE LOWER(email) = ?
            """,
            (email,),
        ).fetchone()

        if user is None:
            print(f"[LỖI] Không tìm thấy tài khoản với email: {email}")
            print("Gợi ý: Người dùng cần đăng ký tài khoản trên ứng dụng trước khi được cấp quyền.")
            return False

        current_role = user["role"]
        is_active = bool(user["is_active"])

        if current_role == role and is_active:
            print("==================================================")
            print(f"THÔNG BÁO: Tài khoản '{user['full_name']}' ({user['email']})")
            print(f"ĐÃ CÓ SẴN vai trò '{role}' ({ROLE_METADATA.get(role, {}).get('name', role)}).")
            print("Không cần thực hiện thay đổi.")
            print("==================================================")
            return True

        if confirm:
            print("--------------------------------------------------")
            print(f"Người dùng: {user['full_name']} ({user['email']})")
            print(f"Vai trò hiện tại: {current_role}")
            print(f"Vai trò mới sẽ cấp: {role} ({ROLE_METADATA.get(role, {}).get('name', role)})")
            print("--------------------------------------------------")
            ans = input("Xác nhận cấp quyền? (y/N): ").strip().lower()
            if ans not in ("y", "yes"):
                print("Đã hủy thao tác.")
                return False

        connection.execute(
            """
            UPDATE users
            SET role = ?,
                is_active = 1
            WHERE id = ?
            """,
            (role, user["id"]),
        )

        # Ghi nhận vào audit logs
        log_admin_activity(
            connection,
            admin_user_id=user["id"],
            action="BOOTSTRAP_ROLE_GRANTED",
            target_type="user",
            target_id=str(user["id"]),
            details=f"Cấp vai trò {role} qua bootstrap CLI (vai trò trước đó: {current_role})",
            result="SUCCESS"
        )

        connection.commit()

        print("==================================================")
        print("✅ ĐÃ CẤP QUYỀN THÀNH CÔNG")
        print("Tên:", user["full_name"])
        print("Email:", user["email"])
        print("Vai trò mới:", role, f"({ROLE_METADATA.get(role, {}).get('name', role)})")
        print("Trạng thái: Hoạt động (is_active = 1)")
        print("==================================================")
        return True

    except Exception as exc:
        connection.rollback()
        print(f"[LỖI DATABASE] Không thể cập nhật quyền: {exc}")
        return False
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description="MediCare AI - Admin RBAC Bootstrap Tool")
    parser.add_argument("--email", "-e", type=str, help="Email của tài khoản cần cấp quyền")
    parser.add_argument(
        "--role",
        "-r",
        type=str,
        default=ROLE_SUPER_ADMIN,
        choices=AVAILABLE_ROLES,
        help="Vai trò cần cấp (mặc định: super_admin)",
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Bỏ qua bước xác nhận tương tác")
    parser.add_argument("--list-roles", action="store_true", help="Liệt kê danh sách các vai trò khả dụng")

    args = parser.parse_args()

    if args.list_roles:
        print("=== DANH SÁCH VAI TRÒ HỆ THỐNG MEDICARE AI ===")
        for r in AVAILABLE_ROLES:
            meta = ROLE_METADATA.get(r, {})
            print(f"- {r.ljust(18)} : {meta.get('name')} — {meta.get('description')}")
        return

    if args.email:
        bootstrap_admin(args.email, args.role, confirm=not args.yes)
        return

    # Interactive prompt mode
    print("==================================================")
    print("      MEDICARE AI — ADMIN RBAC BOOTSTRAP         ")
    print("==================================================")
    email = input("Nhập email tài khoản: ").strip().lower()
    if not email:
        print("Chưa nhập email. Thoát.")
        return

    print("\nChọn vai trò cần cấp:")
    for idx, r in enumerate(AVAILABLE_ROLES, start=1):
        meta = ROLE_METADATA.get(r, {})
        print(f"  {idx}. {r.ljust(18)} : {meta.get('name')}")

    choice = input("\nNhập số thứ tự [1-5] (Mặc định 1 - super_admin): ").strip()
    selected_role = ROLE_SUPER_ADMIN
    if choice in ("1", "2", "3", "4", "5"):
        selected_role = AVAILABLE_ROLES[int(choice) - 1]

    bootstrap_admin(email, selected_role, confirm=True)


if __name__ == "__main__":
    main()