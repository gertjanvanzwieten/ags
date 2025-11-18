class AGSError(ValueError):
    def __init__(self, message, context):
        self.message = message
        self.context = context
        super().__init__(f"{message} in {context}" if context else message)
