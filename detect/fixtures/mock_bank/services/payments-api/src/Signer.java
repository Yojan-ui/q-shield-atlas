import java.security.*;

public class Signer {
    void init() throws Exception {
        KeyPairGenerator k = KeyPairGenerator.getInstance("RSA");
        Signature s = Signature.getInstance("SHA256withRSA");
    }
}
