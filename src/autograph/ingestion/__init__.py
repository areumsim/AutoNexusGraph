"""AutoGraph ingestion — raw 원본을 data/raw/auto/ 에 멱등 저장.

원칙 (finance와 동일):
- 원본 보존 (data/raw/auto/<source>/)
- RateLimiter + CheckpointStore (resume 안전)
- 인증키가 필요한 소스는 키 없을 시 graceful skip + TODO 명시
"""
