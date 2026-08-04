"""The Conversation Engine: ask, answer, carry the navigation forward.

    Question (structured, or parsed from a declared vocabulary)
        -> the handler registered for its intent
        -> an Answer assembled from artifacts that already exist
        -> an updated NavigationContext
        -> a turn appended to the ConversationSession

The engine owns no intelligence. It sequences handlers, guards the citation
law, and carries navigation state. Every answer it returns was assembled from a
finished investigation, and asking any number of questions leaves that
investigation byte-identical.
"""

from __future__ import annotations

from veritriage.conversation.context import ConversationContext
from veritriage.conversation.parse import parse, vocabulary
from veritriage.conversation.registry import get_handler
from veritriage.models import (
    Answer,
    AnswerSection,
    ConversationSession,
    ConversationTurn,
    Intent,
    NavigationContext,
    Question,
)


class ConversationEngine:
    """One navigable conversation over one finished investigation."""

    def __init__(
        self,
        context: ConversationContext,
        session: ConversationSession | None = None,
    ) -> None:
        self._context = context
        self._session = session or ConversationSession(session_id=context.session_id)

    @property
    def session(self) -> ConversationSession:
        """The accumulated exchange. Serializable; the platform stores nothing."""
        return self._session

    @property
    def context(self) -> NavigationContext:
        return self._session.context

    # --- Asking -------------------------------------------------------------

    def ask(self, question: Question | str) -> Answer:
        """Answer one question and carry the navigation forward."""
        parsed = self._as_question(question)
        if parsed is None:
            answer = self._out_of_vocabulary(str(question))
            self._record(Question(intent=Intent.HELP, text=str(question)), answer)
            return answer

        handler = get_handler(parsed.intent)
        if handler is None:
            answer = Answer(
                intent=parsed.intent,
                question=parsed.text or parsed.intent.value,
                summary=f"Nothing is registered to answer a {parsed.intent.value} question.",
                limitations=["No handler is registered for this intent."],
                resolved=False,
            )
            self._record(parsed, answer)
            return answer

        try:
            answer, navigation = handler.answer(parsed, self._context, self.context)
        except Exception as exc:  # one broken handler must not end a conversation
            answer = Answer(
                intent=parsed.intent,
                question=parsed.text or parsed.intent.value,
                summary="That question could not be answered.",
                limitations=[
                    f"The {parsed.intent.value} handler failed ({type(exc).__name__}); "
                    "the investigation itself is unaffected."
                ],
                resolved=False,
            )
            navigation = self.context

        answer = self._verify(answer)
        self._record(parsed, answer, navigation)
        return answer

    def ask_all(self, questions: list[Question | str]) -> list[Answer]:
        """Ask several questions in order, carrying context between them."""
        return [self.ask(question) for question in questions]

    # --- Internals ----------------------------------------------------------

    @staticmethod
    def _as_question(question: Question | str) -> Question | None:
        return question if isinstance(question, Question) else parse(question)

    def _out_of_vocabulary(self, text: str) -> Answer:
        """An honest miss: what was asked, and what can be asked instead.

        Guessing at an unparsed question would be the one thing this layer must
        never do, so it declares its vocabulary instead.
        """
        return Answer(
            intent=Intent.HELP,
            question=text,
            summary="That phrasing is outside the vocabulary this platform understands.",
            sections=[
                AnswerSection(heading="Phrasings understood", statements=vocabulary())
            ],
            followups=[
                Question(intent=Intent.HELP),
                Question(intent=Intent.WHY, target=None),
                Question(intent=Intent.SUMMARIZE, target="agents"),
            ],
            limitations=[
                "Questions are matched against a declared vocabulary, never guessed at. "
                "Ask in one of the forms above, or send a structured Question."
            ],
            resolved=False,
        )

    def _verify(self, answer: Answer) -> Answer:
        """Drop any citation that does not resolve, and say so if any did not.

        The citation law enforced rather than trusted: a handler that names an
        evidence node the graph does not contain has that reference removed and
        the omission recorded, so an unresolvable citation can never reach a
        client.
        """
        kept: list = []
        dropped = 0
        for reference in answer.references:
            if reference.kind.value == "evidence" and not self._context.has_node(
                reference.ref_id
            ):
                dropped += 1
                continue
            if reference not in kept:
                kept.append(reference)
        if dropped == 0 and len(kept) == len(answer.references):
            return answer
        limitations = list(answer.limitations)
        if dropped:
            limitations.append(
                f"{dropped} citation(s) did not resolve to evidence in this run and "
                "were removed."
            )
        return answer.model_copy(update={"references": kept, "limitations": limitations})

    def _record(
        self,
        question: Question,
        answer: Answer,
        navigation: NavigationContext | None = None,
    ) -> None:
        after = navigation if navigation is not None else self.context
        self._session.turns.append(
            ConversationTurn(
                index=len(self._session.turns),
                question=question,
                answer=answer,
                context_after=after,
            )
        )
        self._session.context = after


def start_conversation(
    report,
    graph,
    session_id: str = "",
    design=None,
) -> ConversationEngine:
    """Open a conversation over one finished investigation."""
    return ConversationEngine(
        ConversationContext(
            session_id=session_id, report=report, graph=graph, design=design
        )
    )
