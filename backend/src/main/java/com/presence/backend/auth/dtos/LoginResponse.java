package com.presence.backend.auth.dtos;

public record LoginResponse(
    String token,
    String email,
    String name,
    String role
) {}