class ErrorPortal(Exception):
    def __init__(self,status,mensaje):
        super().__init__(mensaje);self.status=status
