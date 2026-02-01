#!/bin/bash
# 测试脚本：完整的 API 功能测试

BASE_URL="http://localhost:8000"

echo "======================================"
echo "  Gemini Business API 测试脚本"
echo "======================================"
echo ""

# 测试 1: 健康检查
echo "📋 测试 1: 健康检查"
echo "-----------------------------------"
HEALTH=$(curl -s "$BASE_URL/api/v1/status/health")
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
echo ""

# 测试 2: 账号状态
echo "📊 测试 2: 账号状态"
echo "-----------------------------------"
ACCOUNTS=$(curl -s "$BASE_URL/admin/accounts")
echo "$ACCOUNTS" | python3 -m json.tool 2>/dev/null || echo "$ACCOUNTS"
echo ""

# 测试 3: OpenAI API（非流式）
echo "💬 测试 3: OpenAI API（非流式）"
echo "-----------------------------------"
RESPONSE=$(curl -s -X POST "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.0-flash-exp",
    "messages": [{"role": "user", "content": "请用中文回复：1+1等于几？"}],
    "stream": false
  }')
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""

# 测试 4: 模型列表
echo "📚 测试 4: 模型列表"
echo "-----------------------------------"
MODELS=$(curl -s "$BASE_URL/v1/models")
echo "$MODELS" | python3 -m json.tool 2>/dev/null || echo "$MODELS"
echo ""

echo "======================================"
echo "  测试完成！"
echo "======================================"
echo ""
echo "如果看到正常的 JSON 响应，说明服务运行正常。"
echo "如果看到错误，请检查："
echo "  1. accounts.json 配置是否正确"
echo "  2. Cookie 是否有效（未过期）"
echo "  3. docker-compose logs 查看详细错误"
