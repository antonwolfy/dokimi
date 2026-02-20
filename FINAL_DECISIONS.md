# Финальные решения (Audio 18:00 UTC)

**Дата:** 2026-02-20 18:00  
**Источник:** Audio transcript от Nikolay

---

## Утверждённые решения

### 1. Генерация вопросов
✅ **Hybrid: RAGAS + LLM**  
"Ну, можем объединить и сделать гибридный RAGAS и LLM."

### 2. Валидация
✅ **Автоматическая локальная проверка**  
"Ну, можешь сделать локальную проверку, пожалуйста."

### 3. Ground Truth
✅ **Без ground answers сначала, потом добавить проверку**  
"Ну да, начни сначала без Ground Answer. Потом перейдем на то, что он будет делать еще и проверку."

### 4. Человеческая оценка
❌ **Не используем**  
"Человека не проверяем на ответ. Человека вообще не используем на ответ."

### 5. Framework
✅ **LangChain**  
"Ну, пожалуйста, сделай LangChain."

### 6. Персоны (КЛЮЧЕВОЕ ИЗМЕНЕНИЕ)
✅ **Автоматическая генерация персон из продукта**  
"Персоны, они не руками задаются. Персоны также должны, то есть, условно мы говорим проект, и система должна сама определить персоны. Предложить, ну и мы можем их сконфигурировать и поправить."

**Процесс:**
1. Указываем проект (oneTBB)
2. Система анализирует проект → предлагает персоны
3. User может сконфигурировать/поправить
4. Финализируем персоны
5. Генерим вопросы для этих персон

### 7. Next Action
✅ **Делай план, обновляй tracking, начинай работу**  
"Ну и да, хорошо, делай план, обновляю себя в tracking и вперед делать."

---

## Ключевые отличия от предыдущих предположений

**Было:** Я предложил 5 фиксированных персон для oneTBB  
**Стало:** Персоны НЕ фиксированные — система должна их сама предложить

**Новый workflow:**
```
Project → Analyze → Propose Personas → User Configures → Generate Questions
```

---

## Архитектурные компоненты

### Новый модуль: Persona Discovery
**Вход:** Project name (oneTBB)  
**Процесс:**
1. Analyze project docs (README, API structure, examples, use cases)
2. Analyze GitHub issues (pain points, common questions)
3. LLM synthesis → propose 5-8 personas with:
   - Name (ML Engineer, HPC Developer, etc.)
   - Description (role, goals, pain points)
   - Skill level (beginner/intermediate/advanced)
   - Key concerns (performance, ease of use, migration, etc.)

**Выход:** JSON список предложенных персон  
**User action:** Review, edit, approve

---

_Ready for implementation plan._
