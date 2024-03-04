import json
from uuid import uuid4
from typing import List, Any, Optional, Dict, Iterator, Callable, Union, Type, Tuple, Literal

from pydantic import BaseModel, ConfigDict, field_validator, Field, ValidationError

from phi.assistant.run import AssistantRun
from phi.knowledge.base import AssistantKnowledge
from phi.llm.base import LLM
from phi.llm.message import Message
from phi.llm.references import References  # noqa: F401
from phi.memory.assistant import AssistantMemory
from phi.storage.assistant import AssistantStorage
from phi.task.task import Task
from phi.task.llm import LLMTask
from phi.tools import Tool, Toolkit, Function
from phi.utils.log import logger, set_log_level_to_debug
from phi.utils.message import get_text_from_message
from phi.utils.merge_dict import merge_dictionaries
from phi.utils.timer import Timer


class Assistant(BaseModel):
    # -*- Assistant settings
    # LLM to use for this Assistant
    llm: Optional[LLM] = None
    # Assistant introduction. This is added to the chat history when a run is started.
    introduction: Optional[str] = None
    # Assistant name
    name: Optional[str] = None
    # Metadata associated with this assistant
    assistant_data: Optional[Dict[str, Any]] = None

    # -*- Run settings
    # Run UUID (autogenerated if not set)
    run_id: Optional[str] = Field(None, validate_default=True)
    # Run name
    run_name: Optional[str] = None
    # Metadata associated with this run
    run_data: Optional[Dict[str, Any]] = None

    # -*- User settings
    # ID of the user participating in this run
    user_id: Optional[str] = None
    # Metadata associated the user participating in this run
    user_data: Optional[Dict[str, Any]] = None

    # -*- Assistant Memory
    memory: AssistantMemory = AssistantMemory()
    # add_chat_history_to_messages=true_adds_the_chat_history_to_the_messages_sent_to_the_llm.
    add_chat_history_to_messages: bool = False
    # add_chat_history_to_prompt=True adds the formatted chat history to the user prompt.
    add_chat_history_to_prompt: bool = False
    # Number of previous messages to add to the prompt or messages.
    num_history_messages: int = 6

    # -*- Assistant Knowledge Base
    knowledge_base: Optional[AssistantKnowledge] = None
    # Enable RAG by adding references from the knowledge base to the prompt.
    add_references_to_prompt: bool = False

    # -*- Assistant Storage
    storage: Optional[AssistantStorage] = None
    # AssistantRun from the database: DO NOT SET MANUALLY
    db_row: Optional[AssistantRun] = None
    # -*- Assistant Tools
    # A list of tools provided to the LLM.
    # Tools are functions the model may generate JSON inputs for.
    # If you provide a dict, it is not called by the model.
    tools: Optional[List[Union[Tool, Toolkit, Callable, Dict, Function]]] = None
    # Allow the assistant to use tools
    use_tools: bool = False
    # Show tool calls in LLM messages.
    show_tool_calls: bool = False
    # Maximum number of tool calls allowed.
    tool_call_limit: Optional[int] = None
    # Controls which (if any) tool is called by the model.
    # "none" means the model will not call a tool and instead generates a message.
    # "auto" means the model can pick between generating a message or calling a tool.
    # Specifying a particular function via {"type: "function", "function": {"name": "my_function"}}
    #   forces the model to call that tool.
    # "none" is the default when no tools are present. "auto" is the default if tools are present.
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    # -*- Available tools
    # If use_tools is True and update_knowledge_base is True,
    # then a tool is added that allows the LLM to update the knowledge base.
    update_knowledge_base: bool = False
    # If use_tools is True and read_tool_call_history is True,
    # then a tool is added that allows the LLM to get the tool call history.
    read_tool_call_history: bool = False

    # -*- Important: this setting determines if the input messages are formatted
    # If True, phidata will add the system prompt, references, and chat history
    # If False, the input messages are sent to the LLM as is
    format_messages: bool = True

    #
    # -*- Prompt Settings
    #
    # -*- System prompt: provide the system prompt as a string
    system_prompt: Optional[str] = None
    # -*- System prompt function: provide the system prompt as a function
    # This function is provided the "Assistant object" as an argument
    #   and should return the system_prompt as a string.
    # Signature:
    # def system_prompt_function(assistant: Assistant) -> str:
    #    ...
    system_prompt_function: Optional[Callable[..., Optional[str]]] = None
    # If True, build a default system prompt using instructions and extra_instructions
    build_default_system_prompt: bool = True
    # -*- Settings for building the default system prompt
    # Assistant description for the default system prompt
    description: Optional[str] = None
    # List of instructions for the default system prompt
    instructions: Optional[List[str]] = None
    # List of extra_instructions added to the default system prompt
    # Use these when you want to use the default prompt but also add some extra instructions
    extra_instructions: Optional[List[str]] = None
    # Add a string to the end of the default system prompt
    add_to_system_prompt: Optional[str] = None
    # If True, add instructions for using the knowledge base to the default system prompt if knowledge base is provided
    add_knowledge_base_instructions: bool = True
    # If True, add instructions for letting the user know that the assistant does not know the answer
    prevent_hallucinations: bool = False
    # If True, add instructions to prevent prompt injection attacks
    prevent_prompt_injection: bool = False
    # If True, add instructions for limiting tool access to the default system prompt if tools are provided
    limit_tool_access: bool = False
    # If True, add the current datetime to the prompt to give the assistant a sense of time
    # This allows for relative times like "tomorrow" to be used in the prompt
    add_datetime_to_instructions: bool = False
    # If markdown=true, add instructions to format the output using markdown
    markdown: bool = False

    # -*- User prompt: provide the user prompt as a string
    # Note: this will ignore the input message provided to the run function
    user_prompt: Optional[Union[List, Dict, str]] = None
    # -*- User prompt function: provide the user prompt as a function.
    # This function is provided the "Assistant object" and the "input message" as arguments
    #   and should return the user_prompt as a Union[List, Dict, str].
    # If add_references_to_prompt is True, then references are also provided as an argument.
    # If add_chat_history_to_prompt is True, then chat_history is also provided as an argument.
    # Signature:
    # def custom_user_prompt_function(
    #     assistant: Assistant,
    #     message: Union[List, Dict, str],
    #     references: Optional[str] = None,
    #     chat_history: Optional[str] = None,
    # ) -> Union[List, Dict, str]:
    #     ...
    user_prompt_function: Optional[Callable[..., str]] = None
    # If True, build a default user prompt using references and chat history
    build_default_user_prompt: bool = True
    # Function to get references for the user_prompt
    # This function, if provided, is called when add_references_to_prompt is True
    # Signature:
    # def references(assistant: Assistant, query: str) -> Optional[str]:
    #     ...
    references_function: Optional[Callable[..., Optional[str]]] = None
    references_format: Literal["json", "yaml"] = "json"
    # Function to get the chat_history for the user prompt
    # This function, if provided, is called when add_chat_history_to_prompt is True
    # Signature:
    # def chat_history(assistant: Assistant) -> str:
    #     ...
    chat_history_function: Optional[Callable[..., Optional[str]]] = None

    # -*- Assistant Output Settings
    # Provide an output model for the responses
    output_model: Optional[Union[str, List, Type[BaseModel]]] = None
    # If True, the output is converted into the output_model (pydantic model or json dict)
    parse_output: bool = True
    # -*- Final LLM response i.e. the final output of this assistant
    output: Optional[Any] = None

    # -*- Assistant Tasks
    # Tasks allow the Assistant to generate a response using a list of tasks
    # If tasks is None or empty, a single default LLM task is created for this assistant
    tasks: Optional[List[Task]] = None
    # Metadata associated with the assistant tasks
    task_data: Optional[Dict[str, Any]] = None

    # debug_mode=True enables debug logs
    debug_mode: bool = False
    # monitoring=True logs Assistant runs on phidata.com
    monitoring: bool = False

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("debug_mode", mode="before")
    def set_log_level(cls, v: bool) -> bool:
        if v:
            set_log_level_to_debug()
            logger.debug("Debug logs enabled")
        return v

    @field_validator("run_id", mode="before")
    def set_run_id(cls, v: Optional[str]) -> str:
        return v if v is not None else str(uuid4())

    @property
    def streamable(self) -> bool:
        return self.output_model is None

    @property
    def llm_task(self) -> LLMTask:
        """Returns an LLMTask for this assistant"""

        _llm_task = LLMTask(
            llm=self.llm.model_copy() if self.llm is not None else None,
            assistant_name=self.name,
            assistant_memory=self.memory,
            add_references_to_prompt=self.add_references_to_prompt,
            add_chat_history_to_messages=self.add_chat_history_to_messages,
            num_history_messages=self.num_history_messages,
            knowledge_base=self.knowledge_base,
            use_tools=self.use_tools,
            show_tool_calls=self.show_tool_calls,
            tool_call_limit=self.tool_call_limit,
            tools=self.tools,
            tool_choice=self.tool_choice,
            update_knowledge_base=self.update_knowledge_base,
            read_tool_call_history=self.read_tool_call_history,
            format_messages=self.format_messages,
            system_prompt=self.system_prompt,
            system_prompt_function=self.system_prompt_function,
            build_default_system_prompt=self.build_default_system_prompt,
            description=self.description,
            instructions=self.instructions,
            extra_instructions=self.extra_instructions,
            add_to_system_prompt=self.add_to_system_prompt,
            add_knowledge_base_instructions=self.add_knowledge_base_instructions,
            prevent_hallucinations=self.prevent_hallucinations,
            prevent_prompt_injection=self.prevent_prompt_injection,
            limit_tool_access=self.limit_tool_access,
            add_datetime_to_instructions=self.add_datetime_to_instructions,
            markdown=self.markdown,
            user_prompt=self.user_prompt,
            user_prompt_function=self.user_prompt_function,
            build_default_user_prompt=self.build_default_user_prompt,
            references_function=self.references_function,
            references_format=self.references_format,
            chat_history_function=self.chat_history_function,
            output_model=self.output_model,
        )
        return _llm_task

    def to_database_row(self) -> AssistantRun:
        """Create a AssistantRun for the current Assistant (to save to the database)"""

        return AssistantRun(
            name=self.name,
            run_id=self.run_id,
            run_name=self.run_name,
            user_id=self.user_id,
            llm=self.llm.to_dict() if self.llm is not None else None,
            memory=self.memory.to_dict(),
            assistant_data=self.assistant_data,
            run_data=self.run_data,
            user_data=self.user_data,
            task_data=self.task_data,
        )

    def from_database_row(self, row: AssistantRun):
        """Load the existing Assistant from an AssistantRun (from the database)"""

        # Values that are overwritten from the database if they are not set in the assistant
        if self.name is None and row.name is not None:
            self.name = row.name
        if self.run_id is None and row.run_id is not None:
            self.run_id = row.run_id
        if self.run_name is None and row.run_name is not None:
            self.run_name = row.run_name
        if self.user_id is None and row.user_id is not None:
            self.user_id = row.user_id

        # Update llm data from the AssistantRun
        if row.llm is not None:
            # Update llm metrics from the database
            llm_metrics_from_db = row.llm.get("metrics")
            if llm_metrics_from_db is not None and isinstance(llm_metrics_from_db, dict) and self.llm:
                try:
                    self.llm.metrics = llm_metrics_from_db
                except Exception as e:
                    logger.warning(f"Failed to load llm metrics: {e}")

        # Update assistant memory from the AssistantRun
        if row.memory is not None:
            try:
                self.memory = self.memory.__class__.model_validate(row.memory)
            except Exception as e:
                logger.warning(f"Failed to load assistant memory: {e}")

        # Update assistant_data from the database
        if row.assistant_data is not None:
            # If assistant_data is set in the assistant, merge it with the database assistant_data.
            # The assistant assistant_data takes precedence
            if self.assistant_data is not None and row.assistant_data is not None:
                # Updates db_row.assistant_data with self.assistant_data
                merge_dictionaries(row.assistant_data, self.assistant_data)
                self.assistant_data = row.assistant_data
            # If assistant_data is not set in the assistant, use the database assistant_data
            if self.assistant_data is None and row.assistant_data is not None:
                self.assistant_data = row.assistant_data

        # Update run_data from the database
        if row.run_data is not None:
            # If run_data is set in the assistant, merge it with the database run_data.
            # The assistant run_data takes precedence
            if self.run_data is not None and row.run_data is not None:
                # Updates db_row.run_data with self.run_data
                merge_dictionaries(row.run_data, self.run_data)
                self.run_data = row.run_data
            # If run_data is not set in the assistant, use the database run_data
            if self.run_data is None and row.run_data is not None:
                self.run_data = row.run_data

        # Update user_data from the database
        if row.user_data is not None:
            # If user_data is set in the assistant, merge it with the database user_data.
            # The assistant user_data takes precedence
            if self.user_data is not None and row.user_data is not None:
                # Updates db_row.user_data with self.user_data
                merge_dictionaries(row.user_data, self.user_data)
                self.user_data = row.user_data
            # If user_data is not set in the assistant, use the database user_data
            if self.user_data is None and row.user_data is not None:
                self.user_data = row.user_data

        # Update task_data from the database
        if row.task_data is not None:
            # If task_data is set in the assistant, merge it with the database task_data.
            # The assistant task_data takes precedence
            if self.task_data is not None and row.task_data is not None:
                # Updates db_row.task_data with self.task_data
                merge_dictionaries(row.task_data, self.task_data)
                self.task_data = row.task_data
            # If task_data is not set in the assistant, use the database task_data
            if self.task_data is None and row.task_data is not None:
                self.task_data = row.task_data

    def read_from_storage(self) -> Optional[AssistantRun]:
        """Load the AssistantRun from storage"""

        if self.storage is not None and self.run_id is not None:
            self.db_row = self.storage.read(run_id=self.run_id)
            if self.user_id is not None and self.db_row is not None and self.db_row.user_id != self.user_id:
                logger.error(f"SECURITY ERROR: User id mismatch: {self.user_id} != {self.db_row.user_id}")
                return None
            if self.db_row is not None:
                logger.debug(f"-*- Loading run: {self.db_row.run_id}")
                self.from_database_row(row=self.db_row)
                logger.debug(f"-*- Loaded run: {self.run_id}")
        return self.db_row

    def write_to_storage(self) -> Optional[AssistantRun]:
        """Save the AssistantRun to the storage"""

        if self.storage is not None:
            self.db_row = self.storage.upsert(row=self.to_database_row())
        return self.db_row

    def add_introduction(self, introduction: str) -> None:
        """Add assistant introduction to the chat history"""

        if introduction is not None:
            if len(self.memory.chat_history) == 0:
                self.memory.add_chat_message(Message(role="assistant", content=introduction))

    def create_run(self) -> Optional[str]:
        """Create a run in the database and return the run_id.
        This function:
            - Creates a new run in the storage if it does not exist
            - Load the assistant from the storage if it exists
        """

        # If a database_row exists, return the id from the database_row
        if self.db_row is not None:
            return self.db_row.run_id

        # Create a new run or load an existing run
        if self.storage is not None:
            # Load existing run if it exists
            logger.debug(f"Reading run: {self.run_id}")
            self.read_from_storage()

            # Create a new run
            if self.db_row is None:
                logger.debug("-*- Creating new assistant run")
                if self.introduction:
                    self.add_introduction(self.introduction)
                self.db_row = self.write_to_storage()
                if self.db_row is None:
                    raise Exception("Failed to create new assistant run in storage")
                logger.debug(f"-*- Created assistant run: {self.db_row.run_id}")
                self.from_database_row(row=self.db_row)
                self._api_log_assistant_run()
        return self.run_id

    def _run(
        self, message: Optional[Union[List, Dict, str]] = None, stream: bool = True, **kwargs: Any
    ) -> Iterator[str]:
        logger.debug(f"*********** Run Start: {self.run_id} ***********")
        # Load run from storage
        self.read_from_storage()

        # Add a default LLMTask if tasks are empty
        _tasks = self.tasks
        if _tasks is None or len(_tasks) == 0:
            _tasks = [self.llm_task]

        # Metadata for all tasks in this run
        task_data: List[Dict[str, Any]] = []
        # Final LLM response after running all tasks
        run_output = ""

        # -*- Generate response by running tasks
        current_task: Optional[Task] = None
        for idx, task in enumerate(_tasks, start=1):
            logger.debug(f"*********** Task {idx} Start ***********")

            # Set previous_task and current_task
            previous_task = current_task
            if previous_task is not None and previous_task.show_output:
                if stream:
                    yield "\n\n"
                run_output += "\n\n"

            current_task = task

            # -*- Prepare input message for the current_task
            current_task_message: Optional[Union[List, Dict, str]] = None
            if previous_task and previous_task.output is not None:
                # Convert current_task_message to json if it is a BaseModel
                if issubclass(previous_task.output.__class__, BaseModel):
                    current_task_message = previous_task.output.model_dump_json(exclude_none=True, indent=2)
                else:
                    current_task_message = previous_task.output
            else:
                current_task_message = message

            # -*- Update Task
            # Add run state to the task
            current_task.run_id = self.run_id
            current_task.assistant_name = self.name
            current_task.assistant_memory = self.memory
            current_task.run_message = message
            current_task.run_task_data = task_data

            # Set output parsing off. This is handled by the run() function
            current_task.parse_output = False

            # -*- Update LLMTask
            if isinstance(current_task, LLMTask):
                # Update LLM
                if current_task.llm is None and self.llm is not None:
                    current_task.llm = self.llm.model_copy()

            # -*- Run Task
            if stream and current_task.streamable:
                for chunk in current_task.run(message=current_task_message, stream=True, **kwargs):
                    if current_task.show_output:
                        run_output += chunk if isinstance(chunk, str) else ""
                        yield chunk if isinstance(chunk, str) else ""
            else:
                current_task_response = current_task.run(message=current_task_message, stream=False, **kwargs)  # type: ignore
                current_task_response_str = ""
                try:
                    if current_task_response:
                        if isinstance(current_task_response, str):
                            current_task_response_str = current_task_response
                        elif issubclass(current_task_response.__class__, BaseModel):
                            current_task_response_str = current_task_response.model_dump_json(
                                exclude_none=True, indent=2
                            )
                        else:
                            current_task_response_str = json.dumps(current_task_response)

                        if current_task.show_output:
                            if stream:
                                yield current_task_response_str
                            else:
                                run_output += current_task_response_str
                except Exception as e:
                    logger.debug(f"Failed to convert task response to json: {e}")

            logger.debug(f"*********** Task {idx} End ***********")

        # -*- Save run to storage
        self.write_to_storage()

        # -*- Send run event for monitoring
        llm_response_type = "text"
        if self.output_model is not None:
            llm_response_type = "json"
        elif self.markdown:
            llm_response_type = "markdown"
        event_info = {
            "tasks": task_data,
        }
        event_data = {
            "user_message": message,
            "llm_response": run_output,
            "llm_response_type": llm_response_type,
            "info": event_info,
            "metrics": self.llm.metrics if self.llm else None,
        }
        self._api_log_assistant_event(event_type="run", event_data=event_data)

        # -*- Update run output
        self.output = run_output

        # -*- Yield final response if not streaming
        if not stream:
            yield run_output
        logger.debug(f"*********** Run End: {self.run_id} ***********")

    def run(
        self, message: Optional[Union[List, Dict, str]] = None, stream: bool = True, **kwargs: Any
    ) -> Union[Iterator[str], str, BaseModel]:
        # Convert response to structured output if output_model is set
        if self.output_model is not None and self.parse_output:
            logger.debug("Setting stream=False as output_model is set")
            json_resp = next(self._run(message=message, stream=False))
            try:
                structured_output = None
                if (
                    isinstance(self.output_model, str)
                    or isinstance(self.output_model, dict)
                    or isinstance(self.output_model, list)
                ):
                    structured_output = json.loads(json_resp)
                elif issubclass(self.output_model, BaseModel):
                    try:
                        structured_output = self.output_model.model_validate_json(json_resp)
                    except ValidationError:
                        # Check if response starts with ```json
                        if json_resp.startswith("```json"):
                            json_resp = json_resp.replace("```json\n", "").replace("\n```", "")
                            try:
                                structured_output = self.output_model.model_validate_json(json_resp)
                            except ValidationError as exc:
                                logger.warning(f"Failed to validate response: {exc}")

                # -*- Update assistant output to the structured output
                if structured_output is not None:
                    self.output = structured_output
            except Exception as e:
                logger.warning(f"Failed to convert response to output model: {e}")

            return self.output or json_resp
        else:
            if stream and self.streamable:
                resp = self._run(message=message, stream=True, **kwargs)
                return resp
            else:
                resp = self._run(message=message, stream=False, **kwargs)
                return next(resp)

    def chat(
        self, message: Union[List, Dict, str], stream: bool = True, **kwargs: Any
    ) -> Union[Iterator[str], str, BaseModel]:
        return self.run(message=message, stream=stream, **kwargs)

    def _chat_raw(
        self, messages: List[Message], user_message: Optional[str] = None, stream: bool = True
    ) -> Iterator[Dict]:
        logger.debug("*********** Assistant Chat Raw Start ***********")
        if self.llm is None:
            raise Exception("LLM not set")

        # Load run from storage
        self.read_from_storage()

        # -*- Add user message to the memory - this is added to the chat_history
        if user_message:
            self.memory.add_chat_message(Message(role="user", content=user_message))

        # -*- Generate response
        batch_llm_response_message = {}
        if stream:
            for response_delta in self.llm.generate_stream(messages=messages):
                yield response_delta
        else:
            batch_llm_response_message = self.llm.generate(messages=messages)

        # -*- Add prompts and response to the memory - these are added to the llm_messages
        self.memory.add_llm_messages(messages=messages)

        # Add llm response to the chat history
        # LLM Response is the last message in the messages list
        llm_response_message = messages[-1]
        try:
            self.memory.add_chat_message(llm_response_message)
        except Exception as e:
            logger.warning(f"Failed to add llm response to memory: {e}")

        # -*- Save run to storage
        self.write_to_storage()

        # -*- Send assistant event for monitoring
        event_data = {
            "user_message": user_message,
            "llm_response": llm_response_message,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "metrics": self.llm.metrics,
        }
        self._api_log_assistant_event(event_type="chat_raw", event_data=event_data)

        # -*- Yield final response if not streaming
        if not stream:
            yield batch_llm_response_message
        logger.debug("*********** Assistant Chat Raw End ***********")

    def chat_raw(
        self, messages: List[Message], user_message: Optional[str] = None, stream: bool = True
    ) -> Union[Iterator[Dict], Dict]:
        if self.tasks and len(self.tasks) > 0:
            raise Exception("chat_raw does not support tasks")
        resp = self._chat_raw(messages=messages, user_message=user_message, stream=stream)
        if stream:
            return resp
        else:
            return next(resp)

    def rename(self, name: str) -> None:
        """Rename the assistant for the current run"""
        # -*- Read run to storage
        self.read_from_storage()
        # -*- Rename assistant
        self.name = name
        # -*- Save run to storage
        self.write_to_storage()
        # -*- Log assistant run
        self._api_log_assistant_run()

    def rename_run(self, name: str) -> None:
        """Rename the current run"""
        # -*- Read run to storage
        self.read_from_storage()
        # -*- Rename run
        self.run_name = name
        # -*- Save run to storage
        self.write_to_storage()
        # -*- Log assistant run
        self._api_log_assistant_run()

    def generate_name(self) -> str:
        """Generate a name for the run using the first 6 messages of the chat history"""
        if self.llm is None:
            raise Exception("LLM not set")

        _conv = "Conversation\n"
        _messages_for_generating_name = []
        try:
            if self.memory.chat_history[0].role == "assistant":
                _messages_for_generating_name = self.memory.chat_history[1:6]
            else:
                _messages_for_generating_name = self.memory.chat_history[:6]
        except Exception as e:
            logger.warning(f"Failed to generate name: {e}")
        finally:
            if len(_messages_for_generating_name) == 0:
                _messages_for_generating_name = self.memory.llm_messages[-4:]

        for message in _messages_for_generating_name:
            _conv += f"{message.role.upper()}: {message.content}\n"

        _conv += "\n\nConversation Name: "

        system_message = Message(
            role="system",
            content="Please provide a suitable name for this conversation in maximum 5 words. "
            "Remember, do not exceed 5 words.",
        )
        user_message = Message(role="user", content=_conv)
        generate_name_messages = [system_message, user_message]
        generated_name = self.llm.response(messages=generate_name_messages)
        if len(generated_name.split()) > 15:
            logger.error("Generated name is too long. Trying again.")
            return self.generate_name()
        return generated_name.replace('"', "").strip()

    def auto_rename_run(self) -> None:
        """Automatically rename the run"""
        # -*- Read run to storage
        self.read_from_storage()
        # -*- Generate name for run
        generated_name = self.generate_name()
        logger.debug(f"Generated name: {generated_name}")
        self.run_name = generated_name
        # -*- Save run to storage
        self.write_to_storage()
        # -*- Log assistant run
        self._api_log_assistant_run()

    ###########################################################################
    # Api functions
    ###########################################################################

    def _api_log_assistant_run(self):
        if not self.monitoring:
            return

        from phi.api.assistant import create_assistant_run, AssistantRunCreate

        try:
            database_row: AssistantRun = self.db_row or self.to_database_row()
            create_assistant_run(
                run=AssistantRunCreate(
                    run_id=database_row.run_id,
                    assistant_data=database_row.assistant_dict(),
                ),
            )
        except Exception as e:
            logger.debug(f"Could not create assistant monitor: {e}")

    def _api_log_assistant_event(self, event_type: str = "run", event_data: Optional[Dict[str, Any]] = None) -> None:
        if not self.monitoring:
            return

        from phi.api.assistant import create_assistant_event, AssistantEventCreate

        try:
            database_row: AssistantRun = self.db_row or self.to_database_row()
            create_assistant_event(
                event=AssistantEventCreate(
                    run_id=database_row.run_id,
                    assistant_data=database_row.assistant_dict(),
                    event_type=event_type,
                    event_data=event_data,
                ),
            )
        except Exception as e:
            logger.debug(f"Could not create assistant event: {e}")

    ###########################################################################
    # Print Response
    ###########################################################################

    def print_response(
        self,
        message: Optional[Union[List, Dict, str]] = None,
        stream: bool = True,
        markdown: bool = False,
        **kwargs: Any,
    ) -> None:
        from phi.cli.console import console
        from rich.live import Live
        from rich.table import Table
        from rich.status import Status
        from rich.progress import Progress, SpinnerColumn, TextColumn
        from rich.box import ROUNDED
        from rich.markdown import Markdown

        if markdown:
            self.markdown = True

        if self.output_model is not None:
            markdown = False
            self.markdown = False
            stream = False

        if stream:
            response = ""
            with Live() as live_log:
                status = Status("Working...", spinner="dots")
                live_log.update(status)
                response_timer = Timer()
                response_timer.start()
                for resp in self.run(message, stream=True, **kwargs):
                    if isinstance(resp, str):
                        response += resp
                    _response = Markdown(response) if self.markdown else response

                    table = Table(box=ROUNDED, border_style="blue", show_header=False)
                    if message:
                        table.show_header = True
                        table.add_column("Message")
                        table.add_column(get_text_from_message(message))
                    table.add_row(f"Response\n({response_timer.elapsed:.1f}s)", _response)  # type: ignore
                    live_log.update(table)
                response_timer.stop()
        else:
            response_timer = Timer()
            response_timer.start()
            with Progress(
                SpinnerColumn(spinner_name="dots"), TextColumn("{task.description}"), transient=True
            ) as progress:
                progress.add_task("Working...")
                response = self.run(message, stream=False, **kwargs)  # type: ignore

            response_timer.stop()
            _response = Markdown(response) if self.markdown else response

            table = Table(box=ROUNDED, border_style="blue", show_header=False)
            if message:
                table.show_header = True
                table.add_column("Message")
                table.add_column(get_text_from_message(message))
            table.add_row(f"Response\n({response_timer.elapsed:.1f}s)", _response)  # type: ignore
            console.print(table)

    def cli_app(
        self,
        user: str = "User",
        emoji: str = ":sunglasses:",
        stream: bool = True,
        markdown: bool = True,
        exit_on: Tuple[str, ...] = ("exit", "bye"),
    ) -> None:
        from rich.prompt import Prompt

        while True:
            message = Prompt.ask(f"[bold] {emoji} {user} [/bold]")
            if message in exit_on:
                break

            self.print_response(message=message, stream=stream, markdown=markdown)
