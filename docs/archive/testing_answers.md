[
  {
    "role": "EMPLOYEE",
    "email": "akhil@acme.test",
    "turns": [
      {
        "prompt": "how am I doing this cycle?",
        "http": 200,
        "seconds": 2.02,
        "response": {
          "status": "ok",
          "intent": "performance",
          "answer": "You have 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.",
          "data": [
            "Strengthen engineering craft",
            "Ship the H1 platform roadmap",
            "Cycle objectives",
            "Cycle objectives",
            "Cycle objectives"
          ],
          "session_id": "ba706da9-3b87-45a6-8f7d-add4dd4edb53"
        }
      },
      {
        "prompt": "show me my goals",
        "http": 200,
        "seconds": 1.58,
        "response": {
          "status": "ok",
          "intent": "performance",
          "answer": "You have 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.",
          "data": [
            "Strengthen engineering craft",
            "Ship the H1 platform roadmap",
            "Cycle objectives",
            "Cycle objectives",
            "Cycle objectives"
          ],
          "session_id": "ba706da9-3b87-45a6-8f7d-add4dd4edb53"
        }
      },
      {
        "prompt": "how is Aarav Rossi doing this cycle?",
        "http": 200,
        "seconds": 1.23,
        "response": {
          "status": "ok",
          "intent": "performance",
          "answer": "No data in your scope.",
          "data": [],
          "session_id": "ba706da9-3b87-45a6-8f7d-add4dd4edb53"
        }
      },
      {
        "prompt": "what about his reviews?",
        "http": 200,
        "seconds": 1.34,
        "response": {
          "status": "ok",
          "intent": "performance",
          "answer": "You have 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.",
          "data": [
            "Strengthen engineering craft",
            "Ship the H1 platform roadmap",
            "Cycle objectives",
            "Cycle objectives",
            "Cycle objectives"
          ],
          "session_id": "ba706da9-3b87-45a6-8f7d-add4dd4edb53"
        }
      },
      {
        "prompt": "who on my team is missing goals?",
        "http": 200,
        "seconds": 1.13,
        "response": {
          "status": "ok",
          "intent": "general",
          "answer": "I'm a read-only performance assistant, so that's outside what I can help with \u2014 but I can tell you about your goals, KPIs, cycle scores, or reviews (within your access). For example: \u201chow am I doing this cycle?\u201d",
          "data": [],
          "session_id": "ba706da9-3b87-45a6-8f7d-add4dd4edb53"
        }
      }
    ]
  },
  {
    "role": "MANAGER",
    "email": "ada@acme.test",
    "turns": [
      {
        "prompt": "how is Akhil Menon doing this cycle?",
        "http": 200,
        "seconds": 1.56,
        "response": {
          "status": "ok",
          "intent": "performance",
          "answer": "Akhil Menon has 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.",
          "data": [
            "Strengthen engineering craft",
            "Ship the H1 platform roadmap",
            "Cycle objectives",
            "Cycle objectives",
            "Cycle objectives"
          ],
          "session_id": "11589708-8149-44be-902a-58c5ec051512"
        }
      },
      {
        "prompt": "what about his goals?",
        "http": 200,
        "seconds": 1.8,
        "response": {
          "status": "ok",
          "intent": "performance",
          "answer": "Akhil Menon has 5 goal(s): Strengthen engineering craft, Ship the H1 platform roadmap, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track.",
          "data": [
            "Strengthen engineering craft",
            "Ship the H1 platform roadmap",
            "Cycle objectives",
            "Cycle objectives",
            "Cycle objectives"
          ],
          "session_id": "11589708-8149-44be-902a-58c5ec051512"
        }
      },
      {
        "prompt": "how many reviews does Aarav Rossi have?",
        "http": 200,
        "seconds": 1.56,
        "response": {
          "status": "ok",
          "intent": "performance",
          "answer": "Aarav Rossi has 1 review(s), 1 open.",
          "data": [
            "1 review(s), 1 open"
          ],
          "session_id": "11589708-8149-44be-902a-58c5ec051512"
        }
      },
      {
        "prompt": "how is Avery Stone doing?",
        "http": 200,
        "seconds": 1.49,
        "response": {
          "status": "ok",
          "intent": "performance",
          "answer": "No data in your scope.",
          "data": [],
          "session_id": "11589708-8149-44be-902a-58c5ec051512"
        }
      },
      {
        "prompt": "who on my team is missing goals?",
        "http": 200,
        "seconds": 3.06,
        "response": {
          "status": "ok",
          "intent": "search",
          "answer": "Everyone on your team has an active goal set.",
          "data": [],
          "session_id": "11589708-8149-44be-902a-58c5ec051512"
        }
      }
    ]
  },
  {
    "role": "HRBP",
    "email": "priya@acme.test",
    "turns": [
      {
        "prompt": "how is Leon Petrova doing?",
        "http": 200,
        "seconds": 1.43,
        "response": {
          "status": "ok",
          "intent": "performance",
          "data": [],
          "answer": "Several people match that name: Leon Petrova (dir.data@acme.test), Leon Petrova (emp102@acme.test). Try their email address.",
          "session_id": "e81928e3-394f-4524-af75-edbe0c3ff1bf"
        }
      },
      {
        "prompt": "how is Ibrahim Vidal doing this cycle?",
        "http": 200,
        "seconds": 1.52,
        "response": {
          "status": "ok",
          "intent": "performance",
          "data": [],
          "answer": "Several people match that name: Ibrahim Vidal (dir.engineering@acme.test), Ibrahim Vidal (emp100@acme.test). Try their email address.",
          "session_id": "e81928e3-394f-4524-af75-edbe0c3ff1bf"
        }
      },
      {
        "prompt": "create a JD for a Senior Data Analyst",
        "http": 200,
        "seconds": 3.08,
        "response": {
          "type": "plan",
          "status": "plan",
          "intent": "write",
          "session_id": "e81928e3-394f-4524-af75-edbe0c3ff1bf",
          "answer": "Create a job description for a Senior Data Analyst.",
          "plan": {
            "id": "3d3a63e0-a56a-4d78-8c39-94b13359fae9",
            "session": "e81928e3-394f-4524-af75-edbe0c3ff1bf",
            "message": "create a JD for a Senior Data Analyst",
            "summary": "Create a job description for a Senior Data Analyst.",
            "confidence": 0.88,
            "steps": [
              {
                "id": "e2fdbaa0-981b-4b6d-b21f-50299d224326",
                "ordinal": 0,
                "action": "create_jd",
                "feel": "navigate",
                "summary": "Open the JD Library to create a JD for \u201cSenior Data Analyst\u201d \u2014 you fill the details and Generate there.",
                "reason": "Opens the JD Library where you fill in the details and generate the JD.",
                "preview": [
                  {
                    "title": "Senior Data Analyst"
                  }
                ],
                "deeplink": "/jd",
                "prefill": {
                  "title": "Senior Data Analyst"
                },
                "candidates": [],
                "status": "pending",
                "result": {}
              }
            ],
            "created_at": "2026-07-22T14:10:38.503519Z"
          }
        }
      },
      {
        "prompt": "delete all reviews for Tariq Novak",
        "http": 200,
        "seconds": 2.01,
        "response": {
          "status": "blocked",
          "intent": "general",
          "data": [],
          "answer": "I can't delete, erase, or destroy data \u2014 there's no such action available to me. I can help you review, draft, summarise, or approve within what you're allowed to see.",
          "session_id": "e81928e3-394f-4524-af75-edbe0c3ff1bf"
        }
      }
    ]
  },
  {
    "role": "ADMIN",
    "email": "admin@acme.test",
    "turns": [
      {
        "prompt": "how is Leon Petrova doing?",
        "http": 200,
        "seconds": 1.46,
        "response": {
          "status": "ok",
          "intent": "performance",
          "data": [],
          "answer": "Several people match that name: Leon Petrova (dir.data@acme.test), Leon Petrova (emp102@acme.test). Try their email address.",
          "session_id": "f1866590-4fef-42ba-8e8f-4df7e249235b"
        }
      },
      {
        "prompt": "how is priya nair doing this cycle?",
        "http": 200,
        "seconds": 1.58,
        "response": {
          "status": "ok",
          "intent": "performance",
          "answer": "Priya Nair has 5 goal(s): Grow craft & collaboration, Deliver cycle objectives, Cycle objectives, Cycle objectives, Cycle objectives. Latest cycle: On track \u2014 behind pace.",
          "data": [
            "Grow craft & collaboration",
            "Deliver cycle objectives",
            "Cycle objectives",
            "Cycle objectives",
            "Cycle objectives"
          ],
          "session_id": "f1866590-4fef-42ba-8e8f-4df7e249235b"
        }
      },
      {
        "prompt": "what can you do?",
        "http": 200,
        "seconds": 0.97,
        "response": {
          "status": "ok",
          "intent": "capability",
          "answer": "I'm your read-only performance assistant. I can summarise your goals, KPIs, cycle scores, and review status \u2014 and, if you manage people, your team's \u2014 all within what you're allowed to see. I can't make changes or approvals. Try: \u201cwhat are my goals?\u201d or \u201chow am I doing this cycle?\u201d",
          "data": [],
          "session_id": "f1866590-4fef-42ba-8e8f-4df7e249235b"
        }
      },
      {
        "prompt": "what is the capital of France?",
        "http": 429,
        "seconds": 0.02,
        "response": {
          "detail": "Chat budget exhausted for this window.",
          "errors": [
            "Global LLM call ceiling (60) reached for this run \u2014 refusing further calls to protect the quota."
          ]
        }
      },
      {
        "prompt": "how is Nadia Ivanov doing?",
        "http": 429,
        "seconds": 0.02,
        "response": {
          "detail": "Chat budget exhausted for this window.",
          "errors": [
            "Global LLM call ceiling (60) reached for this run \u2014 refusing further calls to protect the quota."
          ]
        }
      }
    ]
  }
]

