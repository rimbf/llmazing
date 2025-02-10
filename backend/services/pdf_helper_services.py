import os
import uuid
import re
from pathlib import Path
import time
from config import Config
from services.document_processing import load_pdf_data, split_docs
from services.embedding_services import load_embedding_model, create_embeddings
from services.qa_chain import load_qa_chain, get_response
from langchain.chat_models import ChatOllama
from langchain.prompts import PromptTemplate
from langchain.callbacks.manager import CallbackManager
from langchain.chains import LLMChain
from langchain.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    ChatPromptTemplate,
)
from services.extract_code import extract_code


class PDFHelperServices:
    def __init__(
        self,
        ollama_api_base_url: str,
        model_name: str = Config.MODEL,
        embedding_model_name: str = Config.EMBEDDING_MODEL_NAME,
    ):
        self._ollama_api_base_url = ollama_api_base_url
        self._model_name = model_name
        self._embedding_model_name = embedding_model_name
        self.temperature = 0.2
        self.information = None
        self.unitTests = None
        self.decisionTree=None

    def set_model_temperature(self, temperature: float):
        """
        Set the temperature for the Llama model.
        """
        self.temperature = temperature

    def ask(self, pdf_file_path: str, question: str) -> str:
        vector_store_directory = os.path.join(
            str(Path.home()),
            "langchain-store",
            "vectorstore",
            "pdf-doc-helper-store",
            str(uuid.uuid4()),
        )
        os.makedirs(vector_store_directory, exist_ok=True)
        llm = ChatOllama(
            temperature=self.temperature,
            base_url=self._ollama_api_base_url,
            model=self._model_name,
            streaming=True,
            top_k=10,
            top_p=0.3,
            num_ctx=3072,
            verbose=False,
        )

        # Load the Embedding Model
        embed = load_embedding_model(model_name=self._embedding_model_name)

        # Load and split the documents
        docs = load_pdf_data(file_path=pdf_file_path)
        documents = split_docs(documents=docs)

        # Create vectorstore
        vectorstore = create_embeddings(
            chunks=documents, embedding_model=embed, storing_path=vector_store_directory
        )

        # Convert vectorstore to a retriever
        retriever = vectorstore.as_retriever()

        template = """
        ### System:
        You are an honest assistant.
        You will accept PDF files and you will answer the question asked by the user appropriately.
        If you don't know the answer, just say you don't know. Don't try to make up an answer.
        ### Context:
        {context}

        ### User:
        {question}

        ### Response:
        """

        prompt = PromptTemplate.from_template(template)

        # Create the chain
        chain = load_qa_chain(retriever, llm, prompt)

        start_time = time.time()
        response = get_response(question, chain)
        end_time = time.time()

        time_taken = round(end_time - start_time, 2)
        print(f"Response time: {time_taken} seconds.\n")

        return response.strip()

    def ask_for_Extract_Information(self, pdf_file_path: str) -> str:
        """
        Extract Information.
        """
        prompt = "You are a legal expert. I am a blockchain developer seeking to extract relevant information from the provided legal contract PDF. Please identify all key clauses and provisions necessary for building a smart contract.Requirements: Focus on clarity and relevance.Do not include any code or technical details."
        self.information = self.ask(pdf_file_path, prompt)
        return self.information

    def update_information(self, edited_information: str) -> str:
        """
        Update the stored information with the edited version.
        """
        self.information = edited_information
        return self.information

    def update_UnitTests(self, edited_unitTests: str) -> str:
        """
        Update the stored information with the edited version.
        """
        # TODO
        print("edited_unitTests", edited_unitTests)
        self.unitTests = edited_unitTests
        return self.unitTests

    def ask_for_generate_unit_test(self, information: str) -> str:
        """
        Generate unit tests for the given information.
        """
        system_message = "You are an expert AI assistant specializing in smart contract development. Your task is to generate comprehensive unit tests for a smart contract according to provided context. Ensure that the tests cover all critical functionalities. The tests should be written in JavaScript and follow best practices for clarity and maintainability."
        prompt = f"""{system_message} Could you write functional tests in JavaScript for a smart contract that implements the following clauses: \n {information} \n The tests should use the Chai assertion library and include a beforeEach block to set up the testing environment. Ensure that the JavaScript tests are syntactically correct and can be compiled without errors. 
        The focus should be solely on functional tests that validate the behavior of the smart contract according to the specified clauses."""
        self.unitTests = self._generate_response(prompt)
        test_folder = "hardhat_test_env/test"
        os.makedirs(test_folder, exist_ok=True)  # Ensure the directory exists
        test_file_path = os.path.join(test_folder, "test.js")
        js_code = re.search(r"```javascript\n(.*?)```", self.unitTests, re.DOTALL)
        if js_code:
            # Write the extracted JavaScript code to a file
            with open(test_file_path, "w") as file:
                self.unitTests = js_code.group(1).strip()
                file.write(self.unitTests)
                print("JavaScript code extracted and saved to test.js.")
        else:
            with open(test_file_path, "w") as file:
                file.write(self.unitTests)
                print("JavaScript code extracted and saved to test.js.")

        return self.unitTests

    def ask_for_decision_tree(self) -> str:
        """
        Generate decision tree for the given unit test.
        """
        escaped_unitTests = self.unitTests.replace("{", "{{").replace("}", "}}")

        system_message = "You are an expert AI assistant specializing in generating decision tree. Your task is to generate comprehensive decision tree of a provided Unit Test."
        #prompt = f"""{system_message} Could you write a decision tree of that unit test: \n {escaped_unitTests} \n . Only decision tree is needed, no code should be included"""

        prompt= f"""Given the following unit test code \n {escaped_unitTests} \n, create a decision tree that outlines the flow of the tests. 
        The tree should include the main categories of tests, the conditions that must be met for each test to pass, and the outcomes for each condition. 
        Use a structured format similar to the example below:
                                Main Category
                                      |
              -------------------------------------------------
              |                                               |
      Condition 1 met?                                   Not met → Outcome 1
              |
   ----------------------------------------------
   |                                            |
Condition 2 met?                               Not met → Outcome 2
   |
Outcome if all conditions are met
   |
   ---------------------------------------------------
   |                                                 |
Next Category Condition met?                     Not met → Outcome 3
   |
Outcome if all conditions are met

Please structure the response in the form of a tree 
"""

        self.decisionTree = self._generate_response(prompt)
        return self.decisionTree


    def ask_for_regenerate_unit_test_eslint(self, results: str) -> str:
        test_file_path = "./hardhat_test_env/test/test.js"
        # Read the contents of the test.js file
        try:
            with open(test_file_path, "r") as file:
                test_code = file.read()
        except FileNotFoundError:
            return f"Error: {test_file_path} not found."

        escaped_test_code = test_code.replace("{", "{{").replace("}", "}}")
        # Construct the prompt with the test code and ESLint results
        prompt = f"""I want you to correct this JS test code based on these results from ESLint:
        
        Test Code:
        {escaped_test_code}
        
        ESLint Results:
        {results}
        
        Note that I want only the corrected code, no other explanations."""

        # Get the corrected code by passing the prompt to your response generation method
        response = self._generate_response(prompt)

        return extract_code(response, "javascript")

    def ask_for_regenerate_unit_test_decision_tree(self, results: str) -> str:
        test_file_path = "./hardhat_test_env/test/test.js"
        # Read the contents of the test.js file
        try:
            with open(test_file_path, "r") as file:
                test_code = file.read()
        except FileNotFoundError:
            return f"Error: {test_file_path} not found."

        escaped_test_code = test_code.replace("{", "{{").replace("}", "}}")
        # Construct the prompt with the test code and ESLint results
        prompt = f"""I want you to update this JS  code based on the given decision tree:
        
        Test Code:
        {escaped_test_code}
        
        \n decision tree:
        {results}
        
        \n Note that this is a test code of a smart contract, so please keep using Chai assertion library and including a beforeEach block to set up the testing environment
        Note that I want only to update JS code based on the given decision tree , no other explanations."""

        # Get the corrected code by passing the prompt to your response generation method
        response = self._generate_response(prompt)

        return extract_code(response, "javascript")


    def ask_for_generate_smart_contract(self) -> str:
        """
        Generate a smart contract based on the provided requirements.
        """
        escaped_unitTests = self.unitTests.replace("{", "{{").replace("}", "}}")
        prompt = f""" You are expert in Blockchain development. Please create a Smart Contract code in solidity according to these requirements:
        1- Terms:\n {self.information}
        2- Functional tests: The Smart Contract should pass these functional tests: \n {escaped_unitTests}.
        3- Specifications: The smart contract should be implemented in Solidity version 0.8.25. It does not include any dependency.Only solidity code should be provided.
        """
        response = self._generate_response(prompt)
        sol_folder = "hardhat_test_env/contracts"
        os.makedirs(sol_folder, exist_ok=True)  # Ensure the directory exists
        sol_file_path = os.path.join(sol_folder, "contract.sol")
        pattern = re.compile(r"```(.*?)```", re.DOTALL)
        matches = pattern.findall(response)

        # Transform each match and ensure SPDX line is included
        updated_matches = []
        for match in matches:
            match = match.strip()
            lines = match.split("\n")
            if lines[0] == "solidity":
                lines = lines[1:]  # Remove "solidity" if present

            # Add SPDX identifier if missing
            if not lines[0].startswith("// SPDX-License-Identifier:"):
                lines.insert(0, "// SPDX-License-Identifier: UNLICENSED")

            # Join lines back and add to updated matches
            updated_match = "\n".join(lines)
            updated_matches.append(updated_match)

        # Update the response with modified matches
        response = "\n\n".join([f"\n{m}\n" for m in updated_matches])

        # Write the updated matches to the Solidity file
        with open(sol_file_path, "w") as fichier:
            for updated_match in updated_matches:
                fichier.write(updated_match + "\n")

        return response

    
    
    def ask_for_regenerate_smart_contract_solc(self, results: str) -> str:
        """
        Regenerate a smart contract based on the provided solc results.
        """

        contract_file_path = './hardhat_test_env/contracts/contract.sol'

        try:
            with open(contract_file_path, 'r') as file:
                contract_code = file.read()
        except FileNotFoundError:
            return f"Error: {contract_file_path} not found."
        
        escaped_contract_code = contract_code.replace("{", "{{").replace("}", "}}")
        escaped_results =  results.replace("{", "{{").replace("}", "}}")

        prompt = f""" I want you to correct the following smart contract code based on these results from solc, adhering to the following rules: 
        1. Ensure the SPDX license identifier remains at the start of the smart contract. 
        2. When a length error occurs for a string attribute, replace 'attribute.length' with 'bytes(attribute).length'.
         Smart Contract:{escaped_contract_code} 
         Solc Results:{escaped_results}
         Provide only the corrected code, no additional explanations or comments."""""
        response = self._generate_response(prompt)

        return extract_code(response, "solidity")
        

    def ask_for_regenerate_smart_contract_slither(self, results: str) -> str:
        """
        Regenerate a smart contract based on the provided slither results.
        """

        contract_file_path = './hardhat_test_env/contracts/contract.sol'

        try:
            with open(contract_file_path, 'r') as file:
                contract_code = file.read()
        except FileNotFoundError:
            return f"Error: {contract_file_path} not found."
        
        escaped_contract_code = contract_code.replace("{", "{{").replace("}", "}}")
        escaped_results =  results.replace("{", "{{").replace("}", "}}")

        prompt = f"""I want you to correct this smart contract code based on these results from slither:
        
        smart contract:
        {escaped_contract_code}
        
        slither Results:
        {escaped_results}
        
        Note that I want only the corrected code, no other explanations."""
        response = self._generate_response(prompt)

        return extract_code(response, "solidity")
    
    
    def ask_for_correct_smart_contract_unit_test_hardhat(self, results: str) -> str:
        """
        Regenerate a smart contract based on the provided hardhat results.
        """

        contract_file_path = './hardhat_test_env/contracts/contract.sol'
        test_file_path = './hardhat_test_env/test/test.js'

        try:
        # Attempt to read both files
            with open(test_file_path, 'r') as test_file:
                test_code = test_file.read()
            with open(contract_file_path, 'r') as contract_file:
                contract_code = contract_file.read()
        except FileNotFoundError as e:
        # Return an error message based on which file was not found
            return f"Error: {e.filename} not found."
        
        escaped_contract_code = contract_code.replace("{", "{{").replace("}", "}}")
        escaped_test_code = test_code.replace("{", "{{").replace("}", "}}")
        escaped_results =  results.replace("{", "{{").replace("}", "}}")

        prompt = f"""I want you to correct this smart contract or/and unit test code based on these results from hardhat:
        
        smart contract:
        {escaped_contract_code}
        
        unit  test:
        {escaped_test_code}

        hardhat Results:
        {escaped_results}
        
        Note that I want only the corrected code, no other explanations."""
        print("#########", prompt)
        response = self._generate_response(prompt)

        smart_contract = extract_code(response, "solidity")
        unit_test = extract_code(response, "javascript")  # Assuming unit test is in JavaScript

        return smart_contract, unit_test
    

    def _generate_response(self, prompt: str) -> str:
        """
        Function to generate a response based on the provided prompt.
        """
        chat_model = ChatOllama(
            callback_manager=CallbackManager([]),
            base_url=self._ollama_api_base_url,
            model=self._model_name,
            temperature=self.temperature,
        )

        # Create prompt templates for system and human interaction
        system_message_prompt = SystemMessagePromptTemplate.from_template(prompt)
        human_message_prompt = HumanMessagePromptTemplate.from_template("{question}")

        # Combine system and human prompts into one chat prompt template
        chat_prompt = ChatPromptTemplate.from_messages(
            [system_message_prompt, human_message_prompt]
        )

        # Create the LLM chain using the chat model and the prompt template
        llm_chain = LLMChain(llm=chat_model, prompt=chat_prompt)

        # Run the LLM chain with a specific question for unit test generation
        response = llm_chain.run({"question": prompt})

        return response.strip()
