import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.Signature;

public class Signer {
    void run() throws Exception {
        KeyPairGenerator kpg = KeyPairGenerator.getInstance("RSA");
        Signature sig = Signature.getInstance("SHA256withECDSA");
        MessageDigest md = MessageDigest.getInstance("SHA-256"); // decoy
    }
}
