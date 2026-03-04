-- Migration: add password_hash column to user_profile
-- This enables email+password registration / login.

ALTER TABLE user_profile
  ADD COLUMN IF NOT EXISTS password_hash VARCHAR(256);
