# Submission traceability report

The supplied material is a build brief, not a PPT file. The mapping below follows its numbered sections and mathematical requirements; slide numbers cannot be verified without the original presentation.

| Requirement | Implementation | Validation |
|---|---|---|
| §1, §3: public benchmark data | `data/ft06.txt`, `data/ft10.txt`, `data/sources.json`, `scripts/fetch_benchmarks.py` | Numeric blocks extracted from the cited OR-Library source; parsing compared directly to asset rows |
| §3: generic TXT/CSV parsing, dimensions, validation | `backend/parser.py`, immutable instance/operation types in `models.py` | Benchmarks, variable-length CSV, spaced/underscored headers, O/Op/Operation labels with numeric ordering, repeated machines, malformed dimensions, indices, durations, duplicate operations, comments and BOM |
| §3, §5: upload/select and persistent instance IDs | `backend/main.py`, `backend/store.py` | JSON selection/text, multipart CSV, UTF-8 error, source exclusivity, parameterized SQLite persistence, missing ID |
| §3: descriptive statistics and lower bound | `backend/stats.py`; frontend Dataset overview | Overall/per-machine min/max/mean/population std, workload, job counts and longest-route/workload bound; unused-machine null distribution |
| §4: job precedence | Both model paths in `backend/solvers.py` | Assertions on actual returned start/end times, independent of model variables |
| §4: disjunctive machine capacity | CP-SAT NoOverlap; CBC binary pair constraints with M=sum(p) | Independent overlap assertions and exhaustive small-instance machine-order enumeration |
| §4: two selectable objectives | Exact makespan and sum of per-machine completion minus workload | Both engines and both objectives checked against independently enumerated optima |
| §4: exact machine completion | CP-SAT maximum equality; CBC final-operation selectors | Returned completion equals the maximum end assigned to each machine, including repeated/unused machines |
| §4: time limit and truthful proof status | `SolveRequest`, CP-SAT status, CBC solution status + proof log | No-incumbent and CBC time-limit tests; bound and gap in common result schema |
| §5: solve endpoint and output schema | `backend/main.py`, Pydantic `SolveResult` | FT06 integration test and feasibility tests; known optimum appears only in test logic |
| §5, §6: arbitrary sensitivity deltas | `backend/sensitivity.py`; Scenario builder, Recharts graph and table | Exact fractional scaling; tests count independent solve calls and verify scaled durations/objectives |
| §6: dynamic Gantt and operation/job/sequence views | `frontend/src/components.tsx`, `frontend/src/App.tsx` | TypeScript production build; coordinates and colors computed from returned operations; focus/hover details and job highlight |
| §6: solver controls and status | Frontend configuration panel, result badges, bounds/gap | Typed live API calls; loading/errors; current configuration distinguished from last result |
| §6: methodology | Frontend Methodology view; README formulation | Assumptions, both constraints/objectives, precision and status semantics documented |
| §7: responsive styling | Tailwind + `frontend/src/styles.css` | Responsive breakpoints, keyboard focus, scrollable tables/timeline, reduced-motion handling |
| §7, §8: setup and deployment | `scripts/dev.py`, Dockerfiles, `compose.yaml`, Nginx configuration | Local frontend/backend startup and HTTP checks; Docker definition provided but Docker unavailable locally |

## Anti-hardcoding audit

- Benchmark job/machine counts, durations and assignments exist as raw numeric data assets and test fixtures only.
- Both engines derive variable ranges, horizon/Big-M and constraint pairs from parsed operations.
- The benchmark selector discovers the `.txt` assets and reads dimensions through the common parser.
- Statistics are recomputed from stored raw input through the same parser.
- Gantt rows, bars, sequences, labels, machine workloads and result metrics use API output.
- Sensitivity starts with an empty input; the user's percentages are validated and each scenario is re-solved.
- Known optimal makespans are not used as hints, answers, stopping conditions or displayed benchmark promises in application code.
- Constants for mathematical identities, indexing, layout, solver settings, and request/numerical safety are not problem data.

## Interpretation choices

Strictly positive durations provide consistent interval/disjunctive behavior across both engines. CSV allows unequal job route lengths; standard OR-Library TXT checks each row against its dimension header. Idle time ends at each machine's last operation, rather than the shared makespan horizon. Exact rational scaling retains fractional sensitivity changes without discretization loss. Uniform scaling is mathematically linear for proven optima, but every scenario still executes the solver. The requested Python stack is retained and shipped with container deployment, rather than replaced with a Workers-compatible solver approximation.
