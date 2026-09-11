# Model-directed multi-agent orchestration для SWE-bench Verified

**Исследовательская записка — 11 сентября 2026.**  Под «subagent» ниже понимается отдельный агентный запуск с собственной траекторией и контекстом, а не просто ещё один tool call. Источники разделены на первичные (документация, исходные prompts, статьи организаций), извлечённые implementation prompts и научные работы/preprints. Последние полезны как свидетельства и дизайн-идеи, но не как доказательство причинного выигрыша на 12 задачах.

## Краткий вывод

Для поставленного контраста наиболее чистый pattern — **model-directed manager–worker (lead-as-manager) с минимальным обязательным substantive-delegation gate**. Lead сохраняет право решать *что* делегировать, сколько агентов вызвать, какой дать scope, ждать ли результат, запускать ли агентов параллельно и как интегрировать ответ. Единственное жёсткое требование treatment: до завершения решить через хотя бы одного subagent не-тривиальную часть ещё нерешённой задачи и использовать её результат. Это не fixed-role pipeline, не mandatory fan-out и не «главный агент без рук».

Это намеренно существенно проще production/research prompt Anthropic. В нём есть ценные принципы делегирования, но он предписывает 1–20 агентов, обычно 3, разный workflow для типов запроса, обязательный параллелизм и детальные исследовательские эвристики. Копирование такого prompt изменило бы не только наличие orchestration, но и reasoning policy, budget, tool use и параллелизм.

Ни одно короткое словесное требование не может *доказать* содержательность делегирования. Поэтому manipulation должна состоять из (i) короткого prompt, (ii) механического completion gate на наличие завершённого subagent run и (iii) заранее зарегистрированного process audit по полным trajectory/logs. Результат следует показывать и intention-to-treat (все запуски treatment), и per-protocol (только прошедшие строгий audit), не подменяя некомплаентные эпизоды незаметным перезапуском.

---

## 1. Что фактически предлагают существующие prompts и системы

### 1.1 Карта подходов

| Источник, автор/организация, контекст | Релевантный фрагмент / точный краткий пересказ | Что решает модель | Что заранее задаёт разработчик | Применимость к данному эксперименту |
|---|---|---|---|---|
| **`research_lead_agent.md`**, Anthropic, Cookbook, production-like deep-research lead; зафиксированный snapshot commit `a97b9a…` [1](https://github.com/anthropics/claude-cookbooks/blob/a97b9a2dc300635f0c26b5e05d0b54bbe0279ee5/patterns/agents/prompts/research_lead_agent.md) | Lead должен оценить запрос, классифицировать его как depth/breadth/straightforward, спланировать, а затем «delegat[e] key tasks». Важные короткие директивы: «default to using 3 subagents», «All substantial information gathering should be delegated», «Avoid overlap», «update … delegation strategy based on findings». | Разбивку конкретного user query; конкретный scope, приоритет, формулировку briefing, источники, адаптацию после ответов и окончательный synthesis. | Обязателен хотя бы 1 агент; таблично предписаны 1, 2–3, 3–5 или 5–10 (max 20) агентов; default 3; lead преимущественно не исследует сам; для всех non-simple запросов обязательны параллельные вызовы; прописаны типы запросов, OODA, budgets и web/internal-tool policy. | **Очень полезный источник принципов, плохой treatment prompt как есть.** Его обязательность delegation отвечает проблеме formal review, но его число, workflow и research-specific instructions — сильные confounds. Подробный разбор — в §2. |
| **Как Anthropic построили Research**, Jeremy Hadfield, Barry Zhang, Kenneth Lien, Florian Scholz, Jeremy Fox, Daniel Ford и команды Anthropic; статья о production Research [2](https://www.anthropic.com/engineering/multi-agent-research-system) | Orchestrator-worker: lead планирует и создаёт specialist subagents, те независимо ищут и возвращают сжатые результаты. Авторы пишут: нужна задача, format ответа, guidance по tools/sources и чёткие границы, иначе появляются gaps/overlap. Lead может добавить агентов или изменить стратегию после результатов. | Число и задачи агентов, выбор следующих направлений, адаптация и synthesis — но внутри prompt-defined policy. | В production prompt — effort tiers, детальные agent counts, guidance начать широко/сузить, parallel calls и source heuristics; реализация в статье в основном синхронно ждёт каждый набор workers. | **Сильное концептуальное основание** для lead-worker и audit trail. Но сами авторы предупреждают: у coding меньше подлинно параллельных подзадач и real-time delegation пока трудна; не оправдывает forced fan-out. |
| **Claude Code: Custom subagents**, Anthropic; продуктовая документация [3](https://code.claude.com/docs/en/sub-agents) и SDK reference [4](https://code.claude.com/docs/en/agent-sdk/subagents) | Subagent — отдельное окно контекста, получает собственный system prompt и task message, а parent получает final report. Документация называет четыре выгоды: isolation, parallelization, specialized instructions, tool restrictions. Для explicit invocation: «mention it by name». | Основной Claude обычно сам решает when-to-delegate по description; может выбрать foreground/background, custom/general-purpose type и содержимое task prompt. | Разработчик задаёт доступные agent definitions, descriptions, system prompts, tool/permission/model limits, concurrency/depth/spend limits; built-in Explore/Plan/general-purpose уже имеют разные возможности. | **Наиболее близкий runtime primitive.** Для эксперимента включить общий `Agent` tool только в treatment, без библиотеки role-specific agents. Subagent с отдельным context — не просто формальный review, если дать ему полноценную траекторию и затем проверить её. |
| **Claude Code: Agent teams**, Anthropic [5](https://code.claude.com/docs/en/agent-teams) | Lead координирует independent Claude sessions; teammates имеют общий task list, mailbox и могут напрямую общаться. Документы рекомендуют teams для независимого research/review, competing debugging hypotheses, new modules и cross-layer work; не рекомендуют для sequential/same-file/many-dependencies. | Lead может решать число teammates и задания; teammates могут self-claim unblocked work. | Feature experimental, требуется interactive session; team introduces shared task list and direct messaging. В документации пример прямо просит «Spawn three teammates» с заданными ролями. | **Не основной выбор для headless SWE-bench.** Team topology и shared board — лишнее вмешательство, а agent teams не запускаются в `-p`/Agent SDK mode. Обычные subagents лучше соответствуют минимальному treatment. |
| **Claude Code: Dynamic workflows**, Anthropic [6](https://code.claude.com/docs/en/workflows) | Claude может написать JavaScript script, который запускает many subagents; таблица прямо различает: у subagents/team «Claude, turn by turn» решает next step, у workflow это решает script. | Модель может написать одноразовый workflow script для конкретной задачи. | После запуска branching, loop и aggregation — детерминированный script; bundled `/deep-research` — fan-out, fetch, cross-check и voting. | **Неподходяще как primary treatment:** переносит ключевую policy из модели в код и особенно полезно для десятков/сотен workers. Может быть отдельным сравнительным condition, но не ответ на question «как делегировать решает модель». |
| **Prompting best practices**, Anthropic [7](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) | Для обычной практики Anthropic рекомендует: иметь well-defined subagent tools и «Let Claude orchestrate naturally»; также предупреждает, что Opus может overuse subagents. Общая рекомендация: ясные прямые instructions, а не избыточная prescriptive цепочка. | Естественный trigger и форма delegation. | Tool surface и prompt остаются developer-defined; предложенный damping prompt исключает subagents для simple/sequential work. | Это **нулевой / natural-orchestration baseline**, но он не решает вашу compliance-проблему: «может делегировать» не равно «должна делегировать substantive work». Минимальная обязательность — сознательное отклонение именно ради manipulation. |
| **Claude 3.5 Sonnet SWE-bench agent**, Anthropic engineering [8](https://www.anthropic.com/engineering/swe-bench-sonnet) | Статья подчёркивает, что SWE-bench измеряет model + scaffold; их философия — «give as much control as possible to the language model» и minimal scaffold. Приведённый prompt предлагает explore → reproduce → edit → rerun → edge cases, но модель свободна в переходах. | Тактика внутри последовательности, tool use, остановка. | Prompt всё же предлагает конкретную solve-loop и запрещает тестовые изменения; Bash/Edit ACI детально определена. | **Хороший шаблон single-agent control**: сохранять base issue prompt, model/version/tools/budget такими же. Не добавлять в multi condition новые советы explore/repro/test — иначе это не чистая orchestration manipulation. |
| **Извлечённые Claude Code prompts**, Piebald-AI, не официальная документация Anthropic; репозиторий заявляет extraction из compiled Claude Code v2.1.268 [9](https://github.com/Piebald-AI/claude-code-system-prompts) | `Subagent delegation restraint`: не делегировать маленькую bounded работу, не fan-out small task и «do not spawn a subagent to review, re-verify, or double-check work you can verify inline»; если делегировал — «do not redo the subagent’s work». `Explore` — read-only file-search specialist [10](https://github.com/Piebald-AI/claude-code-system-prompts/blob/e46a5fc17db670fba5b511ddac69bfcc362bf09f/system-prompts/system-prompt-subagent-delegation-restraint.md). | Выбор независимой sizeable track, части исходного briefing и дальнейшего use report. | Дефолт ориентирован на экономию cost/latency, против формального review и против избыточной delegation; built-in Explore фиксирует read-only роль. | **Полезный implementation evidence и важный конфликт.** Ваш multi prompt должен явным образом override tendency «do it inline», но не должен копировать их size/parallel heuristics. Это third-party snapshot, поэтому не следует называть его официально опубликованным Claude system prompt. |
| **Oh My Pi (OMP)**, Can Bölük, terminal coding harness; `orchestrate` keyword injects hidden notice [11](https://github.com/can1357/oh-my-pi/blob/3b3a6dc9bbd85102ce19d0b1c11bf6870915f6ec/packages/coding-agent/src/modes/orchestrate.ts) и prompt [12](https://github.com/can1357/oh-my-pi/blob/3b3a6dc9bbd85102ce19d0b1c11bf6870915f6ec/packages/coding-agent/src/prompts/system/orchestrate-notice.md) | Exact implementation stance: «Decompose, dispatch, verify, iterate»; substantial/parallelizable work идёт в `task` subagents, trivial inline. Child prompt поручает общий validation lead, поскольку concurrent siblings могут создать phantom failures [13](https://github.com/can1357/oh-my-pi/blob/3b3a6dc9bbd85102ce19d0b1c11bf6870915f6ec/packages/coding-agent/src/prompts/system/subagent-system-prompt.md). | Локальное разбиение после перечисления work surface; scopes; зависимость; corrective task после неудачи. | Очень жёстко: «Parallelize maximally», «NEVER launch one-off task», disjoint edits обязаны быть parallel в одном message; план-фазы, explicit target paths, verification between phases; child не может сам форматировать/валидировать. | **Антипример для вашего primary treatment, но хороший engineering contrast.** Он гарантирует настоящую orchestration ценой принудительного параллелизма, phase gates, e2e/testing advice и exhaustive planning — все могут улучшить/ухудшить SWE outcome независимо от multi-agentness. |
| **AOrchestra**, Jianhao Ruan et al., DeepWisdom/HKUST(GZ) et al.; dynamic subagent creation, включая SWE-bench [14](https://arxiv.org/html/2602.03786) и реализация SWE main prompt [15](https://github.com/FoundationAgents/AOrchestra/blob/14a1a2051d6b03c479b706f8f555a60b8419e3b5/aorchestra/prompts/swebench.py) | MainAgent имеет практически только `delegate_task` или `submit`: проверяет history, выбирает worker model и следующую task. Авторы описывают agent как runtime 4-tuple ⟨instruction, context, tools, model⟩ и создают workers on demand. | Scope очередного task, context, модель и следующий delegate/submit. | Центральному агенту отняты обычные code-navigation/edit tools; strict JSON, attempt budget и submit logic; workers получают автономный ACI prompt. | **Лучший найденный пример технического запрета lead-самоисполнения**, но не чистый contrast: запрет main work и role/model routing меняют capability/interface. Не применять его no-hands constraint, если цель — изолировать обязательность delegation. |
| **CAID: Centralized Asynchronous Isolated Delegation**, Jiayi Geng & Graham Neubig, CMU / OpenHands [16](https://arxiv.org/html/2603.21489) | Manager строит dependency graph, создаёт isolated worktree, workers implement/test/commit; по завершении manager merge и *dynamically updates* plan. Авторы находят diminishing returns, когда parallel agents больше, чем реальных независимых tasks. | Dependency graph, assignment, reassignment после merge, количество/степень parallelism в пределах лимита. | Центральный manager, isolated worktrees, branch-merge, structured JSON, workers self-verify, fixed integration protocol. Результаты относятся к Commit0 и PaperBench, не SWE-bench Verified. | **Сильное evidence против обязательного fan-out** и за явную integration policy. Но его pipeline/worktree/merge дают огромный confound и ориентирован на long-horizon multi-task work, не на один SWE issue. |
| **SWE-Edit**, Yikai Zhang et al., Microsoft/Stanford/UW [17](https://arxiv.org/html/2604.26102) | Fixed interface decomposition: Viewer находит task-relevant code; Editor выполняет natural-language edit; main reasoning остаётся между ними. Авторы сообщают +2.1 pp и −17.9% inference cost на SWE-bench Verified в собственном protocol. | План/вопрос к Viewer и edit instruction. | Ровно две фиксированные роли, типы входа/выхода и trained editor; это не open delegation topology. | **Важное доказательство, что localization и edit могут быть substantive**, но это отдельная architectural intervention, не ваш model-directed condition. Не включать fixed Viewer/Editor как treatment. |
| **MetaGPT**, Sirui Hong et al., DeepWisdom/KAUST et al. [18](https://arxiv.org/html/2308.00352v7), и **ChatDev**, Chen Qian et al., Tsinghua/partners [19](https://arxiv.org/html/2307.07924) | MetaGPT кодирует SOP, assembly line и роли (PM/architect/engineer), structured intermediate artifacts. ChatDev задаёт chat chain между design/coding/testing ролями и communicative dehallucination. | Локальные ответы агентов в предписанных handoffs. | Роли, порядок phases, communication topology и expected artifacts заранее написаны авторами. | **Не соответствуют вопросу.** Это fixed role/workflow MAS; полезны как противоположный полюс, показывающий, чего не нужно невольно добавить в prompt. |
| **AutoGen / OpenAI Agents SDK**, Microsoft Research [20](https://www.microsoft.com/en-us/research/publication/autogen-enabling-next-gen-llm-applications-via-multi-agent-conversation-framework/) и OpenAI docs [21](https://developers.openai.com/api/docs/guides/agents/orchestration) | AutoGen делает conversation patterns программируемыми. OpenAI различает handoff (specialist владеет следующей веткой) и agents-as-tools (manager сохраняет final answer); второе прямо предназначено для bounded subtask и synthesis. | LLM может выбрать tool/handoff из доступных. | Developer определяет список specialists, descriptions, handoff graph, guardrails и часто routing policy. | **Полезная терминология:** ваш pattern — manager/agents-as-tools, а не handoff ownership. Но готовый framework не гарантирует substantive work сам по себе. |
| **BenchAgent: Do More Agents Help?**, Yuhang Fu et al., Westlake/BUPT et al. (preprint) [22](https://arxiv.org/html/2606.05670) | Центральный аргумент: accuracy смешивает workflow с разными tools, budget, answer contract и logging; их framework нормализует substrate и фиксирует workflow как изменяемый слой. В их controlled setting большинство fixed MAS не превосходят matched single agent. | Зависит от сравниваемого workflow. | Общий loader, tool access, accounting, logger и evaluator. | **Наиболее прямое методологическое предупреждение.** Не интерпретировать разницу как effect orchestration, если multi condition получает больше суммарных tokens, tools или solution advice. Это preprint, не окончательный консенсус. |
| **SWE Atlas**, Miguel Romero Calvo et al., Scale AI (preprint) [23](https://arxiv.org/html/2605.08366) | В case study native Claude Code/Gemini explicit dispatch доступен, но Gemini invokes subagent лишь примерно в 1%/0.3% trials и effectively работает как single-agent loop. | Нативные модели могут просто не вызвать доступный tool. | Harness/tool exposure и task type. | Это эмпирическая мотивация для **обязательной**, а не merely-available delegation. Результат про Codebase Q&A, не causal SWE-bench repair experiment. |

### 1.2 Сравнение в одной оси

Есть четыре разных вещи, которые часто ошибочно называют «multi-agent».

1. **Natural optional delegation**: subagent tool доступен, и lead сам может им воспользоваться (Anthropic best practices, обычный Claude Code). Это максимально автономно, но не гарантирует treatment.
2. **Model-directed manager–worker**: lead сохраняет user-facing ответственность и вызывает workers как bounded capabilities; topology/task boundary/ordering выбираются по ходу (Research lead по духу, обычные Claude Code subagents, AOrchestra по идее). Это нужный family.
3. **Fixed specialist workflow/SOP**: заранее стоят planner → coder → tester → reviewer либо Viewer/Editor. Это может быть эффективным, но отвечает на другой вопрос: effect конкретного workflow/role design.
4. **Scripted fan-out/agent teams/branch-and-merge**: orchestration policy частично или полностью живёт в runtime script/shared board/merge protocol. Это изучает test-time scaling, latency или long-horizon coordination, но уже не чистый выбор модели «как делегировать».

Вам нужен (2), с ровно одним нижним ограничением из-за угрозы noncompliance. Не нужен (1), потому что примерно 12 trajectories легко дадут ноль delegation; не нужны (3–4), потому что они вносят значительно больше manipulation.

---

## 2. Подробный разбор `research_lead_agent.md`

### 2.1 Что именно делает lead

Это не короткий «используй агентов при необходимости». Это тщательно прописанный controller prompt примерно на 155 строк, работающий с отдельным research-subagent prompt. Его логика следующая.

**1. Lead сначала строит представление о задаче.** Он обязан разобрать concepts, entities, relationships, нужные facts, temporal constraints, пользовательские ожидания, формат будущего отчёта. Затем явно должен рассмотреть «at least 3» способа ответить и выбрать лучший. Это сильное заставление планировать, а не нейтральный access к workers.

**2. Выбирает topology из taxonomy запроса.**

* *Depth-first* — один вопрос, несколько конкурирующих методов/перспектив; prompt говорит определить 3–5 approaches, expert viewpoints и синтез.
* *Breadth-first* — разные независимо исследуемые subquestions; lead перечисляет subquestions, приоритизирует и задаёт «extremely clear» границы без overlap.
* *Straightforward* — один direct research path; всё равно один comprehensive subagent.

Таким образом, число и содержимое workers не полностью hard-coded: они следуют анализу конкретной query. Но сама taxonomy и требование применить соответствующую ветвь hard-coded.

**3. Выбирает количество, но в очень узких рамках.** Таблица `subagent_count_guidelines` жёстко требует 1 worker даже для simple query, 2–3 для standard, 3–5 для medium, 5–10 (maximum 20) для high complexity. В другом месте содержится «default to using 3 subagents for most queries». Поэтому утверждение, что этот lead сам свободно выбирает число, верно лишь условно: он выбирает *внутри заданного developer budget/tiers*.

**4. Определяет границы и избавляется от overlap.** Для breadth-first задач prompt особенно хорош: выбрать лишь critical components; не плодить agent на every angle; приоритизировать по importance/complexity; дать каждой подзадаче distinct, crisp boundary; заранее указать expected output и aggregation. В `delegation_instructions` есть явное «Avoid overlap between subagents». Anthropic engineering post описывает практическую причину: короткое vague «research semiconductor shortage» приводило к тому, что три агента повторяли 2025 supply-chain search, а другой исследовал 2021 crisis [2](https://www.anthropic.com/engineering/multi-agent-research-system).

**5. Решает sequential против parallel, но с сильным bias.** Семантически lead учитывает priority и dependencies: blocking fact сначала; depth-first perspectives prompt предлагает «in sequence»; breadth-first — в порядке topic importance/complexity. Однако implementation-level правила затем почти снимают свободу: для любого не straightforward запроса `MUST use parallel tool calls` для создания нескольких subagents; «typically running 3 … at the same time». Следовательно, это не нейтральный dynamic scheduler, а research-optimized parallel-first scheduler.

**6. Пишет плотный contract каждому worker.** В брифинге должны быть один core objective, expected output, background, questions, likely sources, tool guidance, reliability criteria и scope boundaries. Связанный `research_subagent.md` требует собственного plan, adaptive tool budget, OODA loop, source-quality assessment, минимум пять tool calls и parallel independent tools [24](https://github.com/anthropics/claude-cookbooks/blob/a97b9a2dc300635f0c26b5e05d0b54bbe0279ee5/patterns/agents/prompts/research_subagent.md). Это объясняет, почему delegation там действительно substantive: worker нельзя вызвать только «проверь ответ» и получить почти пустой single message.

**7. Адаптирует план.** После ответов lead «continuously monitor[s] progress», обновляет search/delegation strategy, применяет Bayesian language к updating priors, закрывает gaps новым worker, но прекращает работу при diminishing returns/time pressure. Диаграмма и статья Anthropic описывают цикл: lead сохраняет plan, запускает *any number* specialists, синтезирует и решает, нужен ли ещё research [2](https://www.anthropic.com/engineering/multi-agent-research-system).

**8. Интегрирует сам, а не перекладывает synthesis.** Самое существенное место: «your primary role is to coordinate, guide, and synthesize — NOT to conduct primary research yourself». Прямой research lead разрешён только для critical gap. Финальный report запрещено делегировать; citation выделен в ещё одного post-processing agent. Таким образом, эта архитектура отделяет *acquisition* (workers) от *integration* (lead).

### 2.2 Модельные решения и навязанные решения

| Оркестрационное решение | Оставлено lead? | Предписано prompt? | Оценка |
|---|---:|---:|---|
| Какие аспекты query существенны | Да | Да, через mandatory assessment checklist | Свобода содержания, но не процесса. |
| Декомпозиция и worker boundaries | Да | Обязательны specific objectives/outputs/boundaries; запрет overlap | Полезно для качества, но добавляет solution-planning treatment. |
| Число workers | Лишь внутри tier | ≥1; default 3; table tiers; max 20 | Несовместимо с «не навязывать число». |
| Роли | Косвенно да: research workers могут получить разные topics/tool scopes | Все являются research subagents с общим procedural prompt | Не фиксированные job titles, но domain/workflow фиксирован. |
| Порядок | Частично: dependencies/importance | Non-simple initial parallel fan-out; depth-first sequence guidance | Несовместимо с полной свободой scheduler. |
| Parallel или sequential | Частично на semantic level | Mandatory parallel calls for multiple agents | Для SWE особенно нежелательно. |
| Перепланирование | Да | Must monitor, Bayesian update, stop at diminishing returns | Хорошая general principle, но «Bayesian» — ненужный advice для clean prompt. |
| Интеграция | Да, исключительно lead | Lead не должен делать primary research и не должен отдавать final report | Для SWE lead должен сам делать значительную диагностику/интеграцию; запрет direct exploration переносить нельзя. |

### 2.3 Что переносится на SWE-bench, а что нет

**Переносимые принципы.**

* Разделять workers не по декоративным названиям, а по *независимому decision-relevant scope*; явно не дублировать одну и ту же диагностику.
* Учитывать зависимость: если diagnosis определяет design, это естественный sequential handoff; если есть две независимые гипотезы или modules — возможен parallel execution.
* Давать worker достаточно task-specific context и ожидаемый результат. Свежий agent не видит parent trajectory; в Claude Code non-fork subagent получает лишь свой prompt, own system prompt, project instructions и tool definitions [4](https://code.claude.com/docs/en/agent-sdk/subagents). Поэтому vague «посмотри проблему» действительно создаёт либо overlap, либо бесполезный report.
* Lead обязан прочитать/использовать report, разрешить расхождения и интегрировать его в patch/test decision. Не поручать final answer агрегатору.
* После отрицательного результата можно менять hypothesis/delegation plan; failure subagent может быть substantive, если lead разумно меняет путь из-за результата.

**Непереносимые или опасные части.**

* В research independent web directions часто abundant. Anthropic прямо пишет, что **coding tasks имеют меньше действительно parallelizable tasks**, а LLM пока не особенно хороши в live coordination [2](https://www.anthropic.com/engineering/multi-agent-research-system). Поэтому «3 workers initially in parallel» может заставить три раза исследовать один stack trace или получить конфликтующие edits.
* Не переносить source-quality policy, web/internal-tool must-use, OODA, «3 approaches», query taxonomy, five-tool-call minimum, budgets, source verification, citation pipeline. Они улучшают исследование сами по себе и не являются orchestration-only manipulation.
* Не переносить `lead must not conduct primary research`. В issue repair lead должен иметь возможность открыть код, увидеть failing test и интегрировать patch; иначе меняется его action space и создаётся AOrchestra-like no-hands confound.
* Не переносить research agent-count table, mandatory parallel calls, minimum tool calls или «default 3». Они отвечают на capacity/latency/cost questions, не на ваш вопрос.

Итого: **переносится логика adaptive delegation и boundary/integration, не переносится дословный prompt.** Ваш treatment берёт только обязательность содержательной части работы и право модели принять все остальные решения.

---

## 3. Что говорят реальные coding implementation prompts

### Claude Code и «официальные system prompts»

Полный главный Claude Code system prompt Anthropic публично не публикует как стабильную нормативную спецификацию. Официальны документация и API contracts: built-in Explore — read-only exploration; Plan — read-only planning research; general-purpose — complex tasks с exploration/action [3](https://code.claude.com/docs/en/sub-agents). Для observability SDK прямо показывает, как детектировать `Agent`/старое `Task` tool-use и `parent_tool_use_id` сообщений child [4](https://code.claude.com/docs/en/agent-sdk/subagents#detect-subagent-invocation).

Piebald — независимый extraction, а не Anthropic source. Тем не менее он особенно информативен для threats to validity: default prompt побуждает lead не создавать child для few reads/one check, не запускать child для review/reverify и не повторять его работу [10](https://github.com/Piebald-AI/claude-code-system-prompts/blob/e46a5fc17db670fba5b511ddac69bfcc362bf09f/system-prompts/system-prompt-subagent-delegation-restraint.md). Иными словами, без вашего explicit requirement сильный coding agent вполне рационально останется single-agent; а formal final-review delegation противоречит даже product default. Его advice по написанию worker briefings тоже говорит не давать fresh agent однострочную команду, а объяснить цель, уже найденное и relevant evidence [25](https://github.com/Piebald-AI/claude-code-system-prompts/blob/e46a5fc17db670fba5b511ddac69bfcc362bf09f/system-prompts/system-prompt-writing-subagent-prompts.md). Не надо вставлять это в experimental prompt; это полезно для harness implementation/аудита.

### Oh My Pi и похожие orchestration harnesses

OMP — почти противоположность minimal manipulation. Его magic word `orchestrate` реально вызывает специальный system notice [11](https://github.com/can1357/oh-my-pi/blob/3b3a6dc9bbd85102ce19d0b1c11bf6870915f6ec/packages/coding-agent/src/modes/orchestrate.ts): запрещает lead делать substantial parallelizable work самому, требует flat todo surface, «parallelize maximally», phase-level gates, scoped target paths и follow-up agents вместо inline repair [12](https://github.com/can1357/oh-my-pi/blob/3b3a6dc9bbd85102ce19d0b1c11bf6870915f6ec/packages/coding-agent/src/prompts/system/orchestrate-notice.md). Child может делать scoped proof, но должен избегать project-wide validation, поскольку siblings меняют дерево одновременно [13](https://github.com/can1357/oh-my-pi/blob/3b3a6dc9bbd85102ce19d0b1c11bf6870915f6ec/packages/coding-agent/src/prompts/system/subagent-system-prompt.md).

Это хорошая production policy для большой change list, но экспериментально она меняет как минимум: planning depth, coverage requirement, number/timing agents, max parallelism, verification frequency, error-correction route, branch behavior и termination. Её не следует использовать даже в смягчённом виде, если outcome должен приписываться обязательности delegation.

CAID демонстрирует другой production engineering выбор: manager строит dependency graph, isolated worktrees предотвращают silent edit interference, merge делает integration явной, а число parallel workers надо согласовать с реальной модульностью [16](https://arxiv.org/html/2603.21489). Это убедительное обоснование *почему не требовать parallelism*. Но CAID также фиксирует именно те operations, которые не должны быть treatment instructions.

AOrchestra решает вашу главную failure mode самым сильным, но слишком грубым способом: MainAgent не имеет code tools и вынужден `delegate_task` до `submit` [15](https://github.com/FoundationAgents/AOrchestra/blob/14a1a2051d6b03c479b706f8f555a60b8419e3b5/aorchestra/prompts/swebench.py). Он динамически выбирает worker configuration, но main-versus-worker capability split — новый intervention. Возьмите от него идею *completion gate*, не запрет lead на repository work.

SWE-Edit показывает допустимые виды substance на реальном SWE setting: repository viewing/localization и deterministic editing могут быть вынесены в clean contexts [17](https://arxiv.org/html/2604.26102). Но fixed Viewer/Editor — готовая delegation topology, поэтому это не ваша manipulation.

### Роль научных multi-agent frameworks

MetaGPT и ChatDev доказывают, что structured intermediate artifacts, role separation и dialogue/SOP бывают полезны [18](https://arxiv.org/html/2308.00352v7) [19](https://arxiv.org/html/2307.07924). Но в обоих design developer уже выбрал «software company»: product manager/architect/engineer, design/coding/testing order, protocol сообщений. Они уместны, когда вопрос — «помогает ли этот simulated-team workflow», но не когда вопрос — «помогает ли model-directed mandatory delegation».

AutoGen и Agents SDK дают полезное разграничение: **handoff** передаёт владение веткой specialist, а **agent-as-tool** сохраняет manager как владельца user-facing answer и synthesis [21](https://developers.openai.com/api/docs/guides/agents/orchestration). Для одной SWE issue нужен второй: lead остаётся интегратором patch, а child не становится финальным владельцем задачи.

Наконец, методологическая литература не поддерживает простое «больше агентов лучше». BenchAgent подчёркивает, что workflow lift нельзя отделить от extra tool access, accounting и answer contract без общего substrate [22](https://arxiv.org/html/2606.05670). CAID эмпирически на своих long-horizon benchmarks видит diminishing returns при agents > number of independent subtasks [16](https://arxiv.org/html/2603.21489). Это не прямой SWE-bench causal result, но достаточное основание не заставлять два/три agents и не фильтровать 12 задач под fan-out.

---

## 4. Рекомендуемый experimental design

### 4.1 Pattern

**Название:** *minimal mandatory, model-directed manager–worker orchestration*.

* **Manager/lead:** тот же coding agent, что в single condition; он может читать, редактировать, запускать tests и завершать задачу.
* **Worker:** любой отдельный child, который lead сам создаёт с выбранным им scope и получает fresh trace/context. Не фиксируйте job title, model tier или task type.
* **Необходимое условие:** `≥1` qualifying substantive child до completion. N может быть 1, 2, …; model решает N. Она также решает sequence/parallelism, whether to resume one child, delegation scope и integration.
* **Необходимое исключение:** completed-patch review / rubber-stamp validation не засчитывается.

Это близко к Anthropic lead-worker architecture и к agents-as-tools, но намеренно не наследует их research-specific policies.

### 4.2 Минимальные ограничения для примерно 12 SWE-bench Verified instances

1. **Заранее зафиксировать выборку.** Опубликовать 12 instance IDs до запуска, sampled/stratified из Verified, а не отобранных по «кажется параллелизуемыми». Минимальная разумная стратификация: repository (не позволять одному repo доминировать), грубая сложность (например, gold patch changed files/LOC tertiles) и тип issue, если метаданные достаточно надёжны. Сохранить exclusions и seed выборки.
2. **Парный within-instance contrast.** Каждый instance запускается в обеих условиях; counterbalance order и interleave runs. Один и тот же model snapshot, system/base prompt, temperature/effort, repository commit/container, test runner, allowed non-agent tools, context policy, wall-clock cap и patch collection/evaluator.
3. **Одинаковый глобальный budget.** Считать *все* lead + child input/output/reasoning tokens, tool calls/CPU и wall-clock. Primary comparison — при одинаковом maximum **total inference cost/tokens** на instance, не per-agent cap. Иначе multi condition получает больше test-time compute; это особенно существенно, потому что Anthropic для BrowseComp связывает 80% variance с token usage и пишет, что multi-agent research расходует примерно 15× chat tokens [2](https://www.anthropic.com/engineering/multi-agent-research-system). Latency и cost можно показать secondary, но не выдавать за чистый accuracy effect.
4. **Одинаковая модель для всех агентных вызовов.** Иначе contrast смешивает orchestration с strong-lead/cheap-worker model routing. Допустим отдельный будущий factor (heterogeneous team), но не здесь.
5. **Single означает действительно single.** В control отключить `Agent`/built-in auto subagents, но не удалять Bash/Edit/Search, доступные lead. В treatment добавить только возможность/обязанность Agent; не добавлять special explorer, reviewer, test skill, web access, worktree или обязательную task board.
6. **Один harness, один patch contract.** Не разрешать multi condition отдельные hidden test scripts, privileged tools или иной git integration. Если child может писать в shared tree, зафиксировать эту семантику для всех children; если runner по необходимости даёт isolated copies, merge mechanism должен быть capability, а не обязательной phase в prompt.
7. **Повторы и интерпретация.** Двенадцать tasks — pilot/exploratory sample, не достаточная база для общего claim о SWE-bench. Один pass меняет resolved rate шагом 1/12 = 8.33 pp. Если ресурс позволяет, запланировать как минимум 3 paired stochastic rollouts на instance (72 run total) с теми же seeds/ordering policy; task-level N всё равно 12, поэтому показывать per-instance table и uncertainty, а не один «значимый» процент. При единственном rollout назвать работу mechanism/feasibility study. Для small-budget сравнений полезен conservative paired multi-seed + BCa/permutation protocol, но даже его авторы рекомендуют under-claim [26](https://arxiv.org/html/2511.19794v1).
8. **Не донастраивать prompt по этим 12.** Разрабатывать и проверять compliance на отдельном development/pilot set. После lock не менять prompt/harness; если изменили — новая preregistered experiment.

### 4.3 Один или два substantive subagents?

**Рекомендация: потребовать минимум одного distinct substantive subagent; не требовать двух и не оставлять число совсем неопределённым.**

* Только «delegation обязательна» без lower bound/evidence позволяет один формальный вызов с пустым review; это не operational condition.
* Один qualifying child — минимальный дозовый порог, который отличает conditions и всё ещё позволяет модели выбрать 1 на последовательной single-file bug или больше на genuinely independent work.
* Два distinct workers искусственно вводят fan-out/ensemble effect и дополнительный compute. Для многих SWE tasks второй worker либо дублирует localization, либо является именно запрещённым final review. Это противоречит документации Anthropic о sequential/same-file dependent work [5](https://code.claude.com/docs/en/agent-teams) и эмпирическому предупреждению CAID о избыточном parallelism [16](https://arxiv.org/html/2603.21489).
* Считать **distinct run**, а не distinct custom role: model может одного агента создать и затем resume, но qualifying delegation должна содержать отдельную child trajectory, не только self-reflection lead.

### 4.4 Запретить final review прямо или только timing?

**Запретить прямо, плюс задать timing через «ещё нерешённая материальная часть».** Одного правила «вызови до final answer» недостаточно: lead может уже internally derive/написать весь patch, а затем до сообщения пользователю попросить «review it». Из log невозможно надёжно наблюдать скрытое reasoning, но можно наблюдать scope и repository state.

Правильное узкое правило — не «никогда не делать review»: independent adversarial validation иногда действительно полезна. Оно такое: **post-hoc review/confirmation completed patch не удовлетворяет обязательному substantive-delegation requirement**. Validation засчитывается лишь если child проверяет ещё открытую гипотезу, создаёт/исполняет discriminator/reproduction, обнаруживает failure и lead меняет/завершает решение с учётом этого. Так запрещается fake compliance, но не модельный выбор использовать validation в настоящем solve-loop.

### 4.5 Требовать parallel fan-out?

**Нет.** Оставить parallel/sequential выбор модели. Parallelism — часть интересующей orchestration policy и отдельный источник latency/compute effects; forced parallelism превращает condition в OMP-style workflow. Для вопроса diagnosis → implementation natural dependency требует sequence; две независимые hypotheses/modules могут оправдать parallelism. Anthropic прямо говорит, что teams хороши когда independent work реально существует, а для sequential/same-file/many dependencies лучше single session/subagents [5](https://code.claude.com/docs/en/agent-teams). В production Research Anthropic ускорил research parallelism, но отдельно оговорил, что coding — худший parallel fit [2](https://www.anthropic.com/engineering/multi-agent-research-system).

### 4.6 Как сохранить treatment чистым

**Control.** Тот же base SWE issue prompt и обычный agent harness; `Agent` disabled; никаких добавочных suggestions «explore/reproduce/test carefully» сверх того, что уже есть в обеих условиях.

**Treatment.** Тот же ровно base prompt + три короткие orchestration sentences из §6; `Agent` enabled; один механический finalization gate на факт завершённого child run. Не добавлять роли, tool budgets, target-file checklist, plan, parallel, verification, testing, worktree, source guidelines, self-critique или «работай дольше». Это важно: даже Article Anthropic про SWE-bench показывает, что prompt/tool scaffold сам существенно меняет score [8](https://www.anthropic.com/engineering/swe-bench-sonnet), а BenchAgent формулирует то же как protocol-alignment threat [22](https://arxiv.org/html/2606.05670).

**Честное ограничение.** Agent tool — неизбежно новая capability именно в treatment. Это не defect, а определение intervention. Претензия должна быть не «effect of same agent with identical action space», а «effect of granting a model-directed multi-agent action and obligating its substantive use при равном total budget». Не заявлять effect «количества моделей» или «лучшего workflow».

---

## 5. Operational definition и проверка substantive delegation

### 5.1 Определение

**Substantive delegation** — это отдельная child trajectory, которую lead запускает, когда остаётся материальная нерешённая часть issue; child самостоятельно выполняет nontrivial task-specific repository work и возвращает проверяемое evidence/artifact; после этого lead использует результат для выбора, изменения или проверки решения до completion.

Это определение требует одновременно **времени, работы и причинной интеграции**, а не просто наличия субагента. Содержательная работа может быть отрицательной: «эта hypothesis отвергнута этим reproduction/test» засчитывается, если она меняет дальнейший путь.

### 5.2 Допустимые области

Следующие области могут быть substantive сами по себе — не надо закреплять их в prompt как роли.

| Область | Когда засчитывается | Когда не засчитывается |
|---|---|---|
| **Localization / repository exploration** | Child независимо прослеживает relevant call path/dependencies, возвращает file:line evidence и это сужает место изменения или отвергает candidate location. SWE-Edit и built-in Explore поддерживают именно такую context-isolated работу [3](https://code.claude.com/docs/en/sub-agents) [17](https://arxiv.org/html/2604.26102). | Один generic `grep`, список файлов без связи с issue или exploration, который lead потом никак не использует. |
| **Diagnosis** | Reproduction, stack trace, root-cause investigation, semantic contrast с expected behavior; report определяет последующий patch/hypothesis. | Пересказ issue или «looks correct» без repo evidence. |
| **Hypothesis generation / design** | Несколько реалистичных implementation hypotheses, grounded в code/tests, с constraints/trade-offs; lead выбирает/исправляет design вследствие ответа. | Общая brainstorming prose без reading/testing и без последующего decision. |
| **Implementation** | Child вносит scoped code artifact/diff либо предлагает точную executable change, которую lead интегрирует/адаптирует; неважно, в shared tree или возвращённом patch, если provenance сохранён. | Lead уже сделал конечный patch, child только форматирует/пересказывает diff. |
| **Debugging** | Child запускает targeted repro/test, выясняет почему candidate fix fails и результат ведёт к следующей попытке. | Повторяет ровно тот же test после complete solution без нового open question. |
| **Test construction** | Создаёт/исполняет targeted reproduction/discriminator или обосновывает missing case, который различает открытые варианты и влияет на patch. Для SWE-bench это может быть temporary local repro, не обязательно изменение benchmark tests. | Постфактум запускает стандартный suite только чтобы поставить галочку. |
| **Validation** | Проверяет ещё не установленную property/candidate approach; находит evidence, которое определяет принять, отвергнуть или изменить решение. | «Review the completed patch», «run tests and approve it» после того, как main уже закончил substantive solve work. |

То есть validation *может* быть substantive, но не в формате final rubber stamp. Это согласуется и с Claude Code docs (subagents полезны для focused research/verification), и с extracted default restraint, который специально не считает inline-review worth subagent overhead [10](https://github.com/Piebald-AI/claude-code-system-prompts/blob/e46a5fc17db670fba5b511ddac69bfcc362bf09f/system-prompts/system-prompt-subagent-delegation-restraint.md).

### 5.3 Предварительно зарегистрированная rubric для trajectory/logs

Ввести бинарный `qualifying_substantive_delegate` только если **все пять** пунктов выполнены хотя бы одним direct child lead.

1. **Identity:** в raw trace есть `Agent`/`Task` invocation lead → child, child final return и связанный `agent_id`/`parent_tool_use_id`.
2. **Scope:** delegation message формулирует конкретный issue-relevant objective, вопрос или bounded deliverable; это не «review/check my finished change» и не purely administrative action.
3. **Unresolved timing:** запуск сделан до observable completion: до final submit/final claim и до состояния, когда lead уже внёс и в trace назвал законченным полный solution patch. Если status неясен, аннотатор консервативно ставит nonqualifying.
4. **Independent work:** child производит task-specific evidence: по умолчанию ≥2 purposeful repository/tool actions (например, read/search + targeted command/read), **или** один directly inspectable code/test/diff artifact. Его final report должен содержать конкретный output (paths/lines, error/test result, hypothesis/design, diff), даже если conclusion negative.
5. **Integration:** после return lead совершает observably связанную action/decision (читает/принимает/отвергает evidence, делает соответствующий edit/test/redelegation) до completion. Простая фраза «thanks» без последствий недостаточна.

Считать также полезные непрерывные process metrics: number of children, direct vs recursive depth, start/finish timestamps, overlap of scopes/files, sequential/parallel graph, child/lead token use, tools per child, reports used, child-generated changed lines, lead edits после report, test commands и merge/conflicts. Это реализует идею *orchestration trace*: не только линейная trajectory, а directed graph spawn → work → return → aggregation [27](https://arxiv.org/html/2605.02801).

**Сбор и audit.**

* Сохранять сырые main/child messages, tool inputs/results, timestamps, token/cost usage by agent, git diff/commits, test output и final evaluator outcome. Claude SDK уже даёт наблюдаемые `Agent` calls и child parent IDs [4](https://code.claude.com/docs/en/agent-sdk/subagents#detect-subagent-invocation); Hooks имеют `SubagentStart`/`SubagentStop` и transcript path [28](https://code.claude.com/docs/en/hooks).
* Два независимых аннотатора, blind к condition label и SWE pass/fail, применяют rubric. Публиковать disagreements, Cohen’s κ и rule of adjudication. Не заменять rubric LLM-judge без human spot check; LLM judge может быть pre-screening, не единственный oracle.
* Runtime hard-gate может проверять только наблюдаемый минимум: до `submit/final`, есть хотя бы один completed `Agent` child. Если его нет — вернуть нейтральное сообщение «subagent delegation is required in this condition», без советов *что* делегировать. Он не должен проверять roles, count, tools, parallelism или советовать debugging. Semantic 5-part compliance оценивается post hoc.
* **Не выбрасывать молча** failed/noncompliant trajectories. Primary ITT включает их как результат treatment; per-protocol ограничивается qualifying runs и явно маркируется selection-sensitive. В ideal pilot prompt/gate должен довести mechanical delegation до 100%, но substantive rate всё равно надо сообщать.

---

## 6. Один рекомендуемый experimental orchestration prompt

Ниже именно добавка к идентичному base SWE-bench prompt в treatment; это не replacement system prompt и не worker prompt.

```text
Use subagent delegation as part of solving this issue. Before you finish, delegate at least one substantive, task-relevant part of the still-unresolved work to a subagent and use its result in the solution; a post-hoc review or trivial confirmation of an already-completed patch does not satisfy this requirement. You decide what to delegate, how many subagents to use, their roles, whether and when to work in parallel or sequentially, and how to integrate their work.
```

Почему именно так:

* **«at least one»** создаёт минимальный проверяемый treatment, не назначая «двух/трёх» или fixed roles.
* **«still-unresolved» + explicit exclusion** закрывают главный formal-review loophole лучше, чем одно «before finish».
* **«substantive, task-relevant»** достаточно general, а его полное operational meaning вынесено в preregistered audit, не в advice model о том, как чинить код.
* Последняя sentence явно сохраняет именно те решения, которые являются исследовательским предметом: scope, count, roles, schedule и integration.
* Здесь нет advice «сначала исследуй», «пиши тест», «используй worktree», «parallelize», «проверь edge cases», «создай план», «работай дольше» или «выполни N tool calls». Любая из таких строк была бы дополнительной performance manipulation.

Не добавляйте в final prompt определение из таблицы областей, требование написать delegation plan или требование отчитаться пользователю об orchestration. Это полезно для audit/protocol, но делает prompt длиннее и превращает минимальную manipulation в tutoring.

---

## 7. Прямые ответы на семь методологических вопросов

1. **Лучший existing pattern:** не MetaGPT/ChatDev SOP и не OMP fan-out, а **manager keeps ownership + subagents-as-bounded-tools**, то есть model-directed lead-worker. По vocabulary OpenAI это agents-as-tools, по Anthropic Research — orchestrator-worker, но с minimal mandatory-substantive gate.
2. **Минимальные ограничения для 12 задач:** frozen preregistered paired task set; same model/tool/base prompt/environment; global total budget including children; actual single-agent control; no fixed roles/workflow/parallelism; raw trace retention; predeclared compliance rubric; и скромная exploratory интерпретация. Добавлять как ограничение «по три агента», «параллельно» или «каждый пишет тест» не нужно.
3. **Сколько workers требовать:** **минимум один distinct substantive subagent**. Это минимальный способ гарантировать contrast; два добавят forced-fan-out confound, а «обязательная delegation без числа» неоперациональна.
4. **Нужно ли прямо запретить main-solves → review:** **да**. Одной temporal формулы недостаточно. Узко исключите only post-hoc review/trivial confirmation completed patch; не запрещайте validation, которая исследует ещё открытую hypothesis и меняет solution.
5. **Parallel fan-out:** **нет**, оставить модели. Это ключевое model-directed decision, и SWE часто serial/dependent.
6. **Формулировка treatment:** identical base prompt плюс три sentence из §6; единственная семантическая разница — mandatory substantive use of subagent. Не добавлять best-practice coding hints, roles, plans или quality gates.
7. **Compliance:** combine mechanical gate (`≥1` completed child before completion) с raw orchestration graph и blinded 5-part substantive rubric. Report ITT and per-protocol, all costs/usage, individual task matrix and failures/noncompliance. Это измеряет не только outcome, но и осуществилась ли сама causal manipulation.

## Источники и границы вывода

* [1](https://github.com/anthropics/claude-cookbooks/blob/a97b9a2dc300635f0c26b5e05d0b54bbe0279ee5/patterns/agents/prompts/research_lead_agent.md), [24](https://github.com/anthropics/claude-cookbooks/blob/a97b9a2dc300635f0c26b5e05d0b54bbe0279ee5/patterns/agents/prompts/research_subagent.md) — первичный, version-pinned Cookbook prompt.
* [2](https://www.anthropic.com/engineering/multi-agent-research-system), [8](https://www.anthropic.com/engineering/swe-bench-sonnet) — Anthropic engineering posts; reported internal results не переносятся автоматически на 12 SWE tasks.
* [3](https://code.claude.com/docs/en/sub-agents), [4](https://code.claude.com/docs/en/agent-sdk/subagents), [5](https://code.claude.com/docs/en/agent-teams), [6](https://code.claude.com/docs/en/workflows), [7](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices), [28](https://code.claude.com/docs/en/hooks) — официальная Claude Code/Platform documentation, подвижна по версии.
* [9](https://github.com/Piebald-AI/claude-code-system-prompts), [10](https://github.com/Piebald-AI/claude-code-system-prompts/blob/e46a5fc17db670fba5b511ddac69bfcc362bf09f/system-prompts/system-prompt-subagent-delegation-restraint.md), [25](https://github.com/Piebald-AI/claude-code-system-prompts/blob/e46a5fc17db670fba5b511ddac69bfcc362bf09f/system-prompts/system-prompt-writing-subagent-prompts.md) — reverse-engineered third-party implementation evidence, не official policy Anthropic.
* [11](https://github.com/can1357/oh-my-pi/blob/3b3a6dc9bbd85102ce19d0b1c11bf6870915f6ec/packages/coding-agent/src/modes/orchestrate.ts), [12](https://github.com/can1357/oh-my-pi/blob/3b3a6dc9bbd85102ce19d0b1c11bf6870915f6ec/packages/coding-agent/src/prompts/system/orchestrate-notice.md), [13](https://github.com/can1357/oh-my-pi/blob/3b3a6dc9bbd85102ce19d0b1c11bf6870915f6ec/packages/coding-agent/src/prompts/system/subagent-system-prompt.md), [15](https://github.com/FoundationAgents/AOrchestra/blob/14a1a2051d6b03c479b706f8f555a60b8419e3b5/aorchestra/prompts/swebench.py) — реальные open-source prompts, pinned to observed commits.
* [14](https://arxiv.org/html/2602.03786), [16](https://arxiv.org/html/2603.21489), [17](https://arxiv.org/html/2604.26102), [22](https://arxiv.org/html/2606.05670), [23](https://arxiv.org/html/2605.08366), [26](https://arxiv.org/html/2511.19794v1), [27](https://arxiv.org/html/2605.02801) — papers/preprints: полезные, но часть claims не peer-reviewed и benchmark/protocol отличаются от этой постановки.
* [18](https://arxiv.org/html/2308.00352v7), [19](https://arxiv.org/html/2307.07924), [20](https://www.microsoft.com/en-us/research/publication/autogen-enabling-next-gen-llm-applications-via-multi-agent-conversation-framework/), [21](https://developers.openai.com/api/docs/guides/agents/orchestration) — foundational/static-role frameworks и composition vocabulary.

Главный вывод не утверждает, что такое condition обязательно повысит SWE-bench score. Он утверждает более скромное и проверяемое: это наиболее чистый способ сделать **обязательную substantive delegation** реально присутствующим treatment, не навязывая модели остальную оркестрацию и не маскируя её effect дополнительными coding best practices.
