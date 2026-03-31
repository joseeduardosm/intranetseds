from __future__ import annotations


def nome_usuario_exibicao(usuario) -> str:
    if not usuario:
        return ""

    try:
        perfil = usuario.ramal_perfil
    except Exception:
        perfil = None

    if perfil:
        nome_perfil = (getattr(perfil, "nome_display", "") or "").strip()
        if nome_perfil:
            return nome_perfil

    nome_completo = (getattr(usuario, "get_full_name", lambda: "")() or "").strip()
    if nome_completo:
        return nome_completo

    primeiro_nome = (getattr(usuario, "first_name", "") or "").strip()
    if primeiro_nome:
        return primeiro_nome

    return (getattr(usuario, "username", "") or "").strip()
